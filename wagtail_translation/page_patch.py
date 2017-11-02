from __future__ import absolute_import, unicode_literals

import logging
import re
import uuid

from django import VERSION as DJANGO_VERSION
from django.core.exceptions import ValidationError
from django.core.urlresolvers import reverse
from django.db import connection, transaction
from django.utils.text import slugify
from django.utils.translation import get_language, ugettext_lazy as _
from modeltranslation import settings as mt_settings
from modeltranslation.utils import (build_localized_fieldname,
                                    get_translation_fields)
from wagtail.wagtailcore.models import Page, Site
from wagtail.wagtailcore.utils import WAGTAIL_APPEND_SLASH

from . import edit_handlers
from .search import search_fields as _search_fields
from .site_patch import delete_root_path_cache
from .utils import page_slug_is_available

logger = logging.getLogger('wagtail.core')

__all__ = ['set_url_path', '_get_autogenerated_lang_slug',
           'full_clean', 'clean', 'save', '_update_descendant_lang_url_paths',
           'get_url_parts', 'move', 'search_fields', 'content_panels', 'promote_panels',
           'base_form_class']

PREFIX = "_UUID_"


def set_url_path(self, parent):
    for lang_code in mt_settings.AVAILABLE_LANGUAGES:
        url_path_attr = build_localized_fieldname('url_path', lang_code)
        slug_attr = build_localized_fieldname('slug', lang_code)
        if parent:
            # When slug has no translation, added url_path part will become '//'
            # which will make this page not accessible in this language
            # because wagtail urls will simply not match it.
            # On the other hand, non empty url_path for every language is important.
            # It makes sure descendant url_path updating keeps working as expected.
            slug = getattr(self, slug_attr, '') or ''
            base_path = getattr(parent, url_path_attr, '') or ''
            new_url_path = base_path + slug + '/'
        else:
            new_url_path = '/'
        setattr(self, url_path_attr, new_url_path)

    return self.url_path  # return current language url_path


def _get_autogenerated_lang_slug(self, base_slug, lang_code):
    candidate_slug = base_slug
    suffix = 1
    parent_page = self.get_parent()

    while not page_slug_is_available(candidate_slug, lang_code, parent_page, self):
        suffix += 1
        candidate_slug = "%s-%d" % (base_slug, suffix)

    return candidate_slug


def full_clean(self, *args, **kwargs):
    # autogenerate slugs for non-empty title translation

    for lang_code in mt_settings.AVAILABLE_LANGUAGES:
        title_field = build_localized_fieldname('title', lang_code)
        slug_field = build_localized_fieldname('slug', lang_code)

        title = getattr(self, title_field)
        slug = getattr(self, slug_field)
        if title and not slug:
            if DJANGO_VERSION >= (1, 9):
                base_slug = slugify(title, allow_unicode=True)
            else:
                base_slug = slugify(title)

            if base_slug:
                setattr(self, slug_field, self._get_autogenerated_lang_slug(base_slug, lang_code))

    # force setting fallback fields to uuid if current language is not set
    # these will not be saved, but will allow us to save the form
    lang_code = get_language() or mt_settings.DEFAULT_LANGUAGE
    title_field = build_localized_fieldname('title', lang_code)
    slug_field = build_localized_fieldname('slug', lang_code)
    if not getattr(self, title_field) or not getattr(self, slug_field):
        dummy_val = "{}{}".format(PREFIX, uuid.uuid4().hex)
        setattr(self, 'title', dummy_val)
        setattr(self, 'slug', dummy_val)

    super(Page, self).full_clean(*args, **kwargs)


def clean(self):
    errors = {}
    for lang_code in mt_settings.AVAILABLE_LANGUAGES:
        slug_field = build_localized_fieldname('slug', lang_code)
        slug = getattr(self, slug_field)
        if slug and not page_slug_is_available(slug, lang_code, self.get_parent(), self):
            errors[slug_field] = _("This slug is already in use")
    if errors:
        raise ValidationError(errors)


@transaction.atomic
def save(self, *args, **kwargs):
    self.full_clean()

    update_descendant_url_paths = False
    is_new = self.id is None

    if is_new:
        self.set_url_path(self.get_parent())
    else:
        # update url paths if:
        # a) update_fields is specified and it includes any slug field
        # or
        # b) update_fields is not specified (check all slug fields in that case)
        slug_fields = get_translation_fields('slug')
        update_fields = kwargs.get('update_fields', slug_fields)
        updated_slug_fields = [f for f in slug_fields if f in update_fields]
        if updated_slug_fields:
            old_record = Page.objects.get(id=self.id)
            if any(getattr(old_record, f) != getattr(self, f) for f in updated_slug_fields):
                self.set_url_path(self.get_parent())
                update_descendant_url_paths = True

    # current language fields may have been set to our uuid,
    # let's get rid of that
    lang_code = get_language() or mt_settings.DEFAULT_LANGUAGE
    xp = re.compile(r"{}[0-9a-f]+".format(PREFIX))

    title_field = build_localized_fieldname('title', lang_code)
    slug_field = build_localized_fieldname('slug', lang_code)
    url_path_field = build_localized_fieldname('url_path', lang_code)
    field_list = [title_field, slug_field, url_path_field, ]

    for field in field_list:
        setattr(self, field, xp.sub("", getattr(self, field)))

    if xp.match(self.draft_title):
        # try to override uuid-draft_title with a nice one
        for lang_code in mt_settings.AVAILABLE_LANGUAGES:
            title_field = build_localized_fieldname('title', lang_code)
            if getattr(self, title_field):
                self.draft_title = getattr(self, title_field)
                break

    result = super(Page, self).save(*args, **kwargs)

    if update_descendant_url_paths:
        self._update_descendant_lang_url_paths(old_record)

    if Site.objects.filter(root_page=self).exists():
        delete_root_path_cache()

    if is_new:
        cls = type(self)
        logger.info(
            "Page created: \"%s\" id=%d content_type=%s.%s path=%s",
            self.title,
            self.id,
            cls._meta.app_label,
            cls.__name__,
            self.url_path
        )

    return result


def _update_descendant_lang_url_paths(self, old_page):
    cursor = connection.cursor()
    if connection.vendor == 'sqlite':
        field_update_fmt = "{0} = %s || substr({0}, %s)"
    elif connection.vendor == 'mysql':
        field_update_fmt = "{0} = CONCAT(%s, substring({0}, %s))"
    elif connection.vendor in ('mssql', 'microsoft'):
        field_update_fmt = "{0} = CONCAT(%s, (SUBSTRING({0}, 0, %s)))"
    else:
        field_update_fmt = "{0} = %s || substring({0} from %s)"

    exec_args = []
    update_fields_sql = []
    for lang_code in mt_settings.AVAILABLE_LANGUAGES:
        url_path_attr = build_localized_fieldname('url_path', lang_code)
        new_url_path = getattr(self, url_path_attr)
        old_url_path = getattr(old_page, url_path_attr)
        if new_url_path != old_url_path:
            update_fields_sql.append(field_update_fmt.format(url_path_attr))
            exec_args.append(new_url_path)
            exec_args.append(len(old_url_path) + 1)

    if not update_fields_sql:
        # in case page was moved but parent did not change
        # nothing has to be updated
        return

    update_sql = """
    UPDATE wagtailcore_page
    SET {} WHERE path LIKE %s AND id <> %s
    """.format(','.join(update_fields_sql))
    exec_args.append(self.path + '%')
    exec_args.append(self.id)
    cursor.execute(update_sql, exec_args)


def get_url_parts(self, request=None):
    # if '//' exists in url_path, it means that some
    # page in the path is not translated, therefore
    # this page is not routable in current language
    if '//' in self.url_path:
        return

    # copy of original implementation:
    for (site_id, root_path, root_url) in self._get_site_root_paths(request):
        if self.url_path.startswith(root_path):
            page_path = reverse('wagtail_serve', args=(self.url_path[len(root_path):],))

            # Remove the trailing slash from the URL reverse generates if
            # WAGTAIL_APPEND_SLASH is False and we're not trying to serve
            # the root path
            if not WAGTAIL_APPEND_SLASH and page_path != '/':
                page_path = page_path.rstrip('/')

            return (site_id, root_url, page_path)


@transaction.atomic
def move(self, target, pos=None):
    old_self = Page.objects.get(id=self.id)
    super(Page, self).move(target, pos=pos)

    new_self = Page.objects.get(id=self.id)
    # go through slugs to make sure they're available in new parent
    # and auto-update if necessary
    for lang_code in mt_settings.AVAILABLE_LANGUAGES:
        slug_attr = build_localized_fieldname('slug', lang_code)
        slug = getattr(new_self, slug_attr)
        if slug:
            slug = new_self._get_autogenerated_lang_slug(slug, lang_code)
            setattr(new_self, slug_attr, slug)
    new_self.set_url_path(new_self.get_parent())
    new_self.save()
    new_self._update_descendant_lang_url_paths(old_self)

    logger.info("Page moved: \"%s\" id=%d path=%s", self.title, self.id, self.url_path)


search_fields = _search_fields

content_panels = edit_handlers.content_panels
promote_panels = edit_handlers.promote_panels
base_form_class = edit_handlers.WagtailAdminTranslatablePageForm
