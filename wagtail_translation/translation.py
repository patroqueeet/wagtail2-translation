from modeltranslation import settings as mt_settings
from modeltranslation.translator import TranslationOptions, register
from wagtail.wagtailcore.models import Page


@register(Page)
class PageTranslationOptions(TranslationOptions):
    fields = (
        'title',
        'slug',
        'seo_title',
        'search_description',
        'url_path',)
    required_languages = getattr(mt_settings, 'REQUIRED_PAGE_LANGUAGES', None)
