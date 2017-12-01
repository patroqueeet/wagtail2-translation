from django import forms
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from modeltranslation import settings as mt_settings
from modeltranslation.utils import build_localized_fieldname
from wagtail.wagtailadmin.edit_handlers import FieldPanel, MultiFieldPanel
from wagtail.wagtailadmin.forms import WagtailAdminPageForm

from .utils import deprecated, get_lang_obj, obj_per_lang, page_slug_is_available


@deprecated
def get_lang_panel(lang_code, panel_cls, field_name, *args, **kwargs):
    return get_lang_obj(lang_code, panel_cls, field_name, *args, **kwargs)


@deprecated
def multiply_panels_per_lang(panel_cls, field_name, *args, **kwargs):
    return obj_per_lang(panel_cls, field_name, *args, **kwargs)


# replacements for Page.content_panels and Page.promote_panels to include translated fields
content_panels = obj_per_lang(FieldPanel, 'title', classname='full title')
promote_panels = [
    MultiFieldPanel(
        obj_per_lang(FieldPanel, 'slug') +
        obj_per_lang(FieldPanel, 'seo_title') +
        [FieldPanel('show_in_menus')] +
        obj_per_lang(FieldPanel, 'search_description'),
        _('Common page configuration')
    )
]


# replacement base form for pages
class WagtailAdminTranslatablePageForm(WagtailAdminPageForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        required_fields = getattr(
            self.instance, "required_translation_fields", [])
        if not required_fields:
            required_fields = [f.name
                               for f in self.instance._meta.local_fields
                               if hasattr(f, "blank") and f.blank is False]
        required_fields = set(required_fields + ['title', 'slug', ])

        for lang_code in mt_settings.AVAILABLE_LANGUAGES:
            for field in required_fields:
                localized = build_localized_fieldname(field, lang_code)
                if localized in self.fields:
                    self.fields[localized].label = "{}*".format(
                        self.fields[localized].label)

    def clean(self):
        cleaned_data = super(WagtailAdminTranslatablePageForm, self).clean()

        required_fields = getattr(
            self.instance, "required_translation_fields", [])
        if not required_fields:
            required_fields = [f.name
                               for f in self.instance._meta.local_fields
                               if hasattr(f, "blank") and f.blank is False]

        for lang_code in mt_settings.AVAILABLE_LANGUAGES:
            slug_field = build_localized_fieldname('slug', lang_code)

            if slug_field in cleaned_data and cleaned_data[slug_field]:
                for field in required_fields:
                    localized = build_localized_fieldname(field, lang_code)
                    if (localized in self.fields and
                            hasattr(self.instance, localized) and not
                            cleaned_data[localized]):
                        self.add_error(
                            localized,
                            forms.ValidationError(_("This field is required")))

                if not page_slug_is_available(
                    cleaned_data[slug_field], lang_code, self.parent_page, self.instance
                ):
                    self.add_error(
                        slug_field,
                        forms.ValidationError(_("This slug is already in use in this language")))

        # Check scheduled publishing fields
        go_live_at = cleaned_data.get('go_live_at')
        expire_at = cleaned_data.get('expire_at')

        # Go live must be before expire
        if go_live_at and expire_at:
            if go_live_at > expire_at:
                msg = _('Go live date/time must be before expiry date/time')
                self.add_error('go_live_at', forms.ValidationError(msg))
                self.add_error('expire_at', forms.ValidationError(msg))

        # Expire at must be in the future
        if expire_at and expire_at < timezone.now():
            self.add_error('expire_at', forms.ValidationError(_('Expiry date/time must be in the future')))

        return cleaned_data
