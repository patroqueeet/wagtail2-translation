from django import forms
from django.conf import settings
from django.utils.translation import ungettext, ugettext as _

from modeltranslation import settings as mt_settings
from modeltranslation.utils import build_localized_fieldname

from wagtail.wagtailadmin import widgets
from wagtail.wagtailcore.models import Page


class CopyForm(forms.Form):
    def __init__(self, *args, **kwargs):
        # CopyPage must be passed a 'page' kwarg indicating the page to be copied
        self.page = kwargs.pop('page')
        self.user = kwargs.pop('user', None)
        can_publish = kwargs.pop('can_publish')
        super(CopyForm, self).__init__(*args, **kwargs)
        for lang in mt_settings.AVAILABLE_LANGUAGES:
            new_title_field = build_localized_fieldname("new_title", lang)
            title_field = build_localized_fieldname("title", lang)
            new_slug_field = build_localized_fieldname("new_slug", lang)
            slug_field = build_localized_fieldname("slug", lang)
            self.fields[new_title_field] = forms.CharField(
                initial=getattr(self.page, title_field),
                label=_("New title [{}]".format(lang)))
            self.fields[new_slug_field] = forms.SlugField(
                initial=getattr(self.page, slug_field),
                label=_("New slug [{}]".format(lang)))

        self.fields['new_parent_page'] = forms.ModelChoiceField(
            initial=self.page.get_parent(),
            queryset=Page.objects.all(),
            widget=widgets.AdminPageChooser(can_choose_root=True, user_perms='copy_to'),
            label=_("New parent page"),
            help_text=_("This copy will be a child of this given parent page.")
        )
        pages_to_copy = self.page.get_descendants(inclusive=True)
        subpage_count = pages_to_copy.count() - 1
        if subpage_count > 0:
            self.fields['copy_subpages'] = forms.BooleanField(
                required=False, initial=True, label=_("Copy subpages"),
                help_text=ungettext(
                    "This will copy %(count)s subpage.",
                    "This will copy %(count)s subpages.",
                    subpage_count) % {'count': subpage_count})

        if can_publish:
            pages_to_publish_count = pages_to_copy.live().count()
            if pages_to_publish_count > 0:
                # In the specific case that there are no subpages, customise the field label and help text
                if subpage_count == 0:
                    label = _("Publish copied page")
                    help_text = _("This page is live. Would you like to publish its copy as well?")
                else:
                    label = _("Publish copies")
                    help_text = ungettext(
                        "%(count)s of the pages being copied is live. Would you like to publish its copy?",
                        "%(count)s of the pages being copied are live. Would you like to publish their copies?",
                        pages_to_publish_count) % {'count': pages_to_publish_count}

                self.fields['publish_copies'] = forms.BooleanField(
                    required=False, initial=True, label=label, help_text=help_text
                )

    def clean(self):
        cleaned_data = super(CopyForm, self).clean()

        # New parent page given in form or parent of source, if parent_page is empty
        parent_page = cleaned_data.get('new_parent_page') or self.page.get_parent()

        # check if user is allowed to create a page at given location.
        if not parent_page.permissions_for_user(self.user).can_add_subpage():
            self._errors['new_parent_page'] = self.error_class([
                _("You do not have permission to copy to page \"%(page_title)s\"") % {'page_title': parent_page.get_admin_display_title()}
            ])

        # Make sure the slug isn't already in use
        for lang in mt_settings.AVAILABLE_LANGUAGES:
            new_slug_field = build_localized_fieldname("new_slug", lang)
            slug_field = build_localized_fieldname("slug", lang)

            slug = cleaned_data.get(new_slug_field)

            # Count the pages with the same slug within the context of our copy's parent page
            if slug and parent_page.get_children().filter(**{slug_field: slug}).count():
                self._errors[new_slug_field] = self.error_class(
                    [_("This slug is already in use within the context of its parent page \"%s\"" % parent_page)]
                )
                # The slug is no longer valid, hence remove it from cleaned_data
                del cleaned_data[new_slug_field]

        # Don't allow recursive copies into self
        if cleaned_data.get('copy_subpages') and (self.page == parent_page or parent_page.is_descendant_of(self.page)):
            self._errors['new_parent_page'] = self.error_class(
                [_("You cannot copy a page into itself when copying subpages")]
            )

        return cleaned_data
