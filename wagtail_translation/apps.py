from importlib import import_module

from django.apps import AppConfig


class WagtailTranslationAppConfig(AppConfig):
    name = 'wagtail_translation'
    label = 'wagtailtranslation'
    verbose_name = 'Wagtail translation'

    def ready(self):
        from django.conf import settings
        # Add Wagtail defined fields as modeltranslation custom fields
        setattr(settings,
                'MODELTRANSLATION_CUSTOM_FIELDS',
                getattr(settings, 'MODELTRANSLATION_CUSTOM_FIELDS', ()) + (
                    'StreamField', 'RichTextField'))

        # patch Site and Page models here
        from wagtail.wagtailcore.models import AbstractPage, Page, Site
        from wagtail.wagtailcore.query import PageQuerySet
        from wagtail.wagtailadmin.views import pages
        from .manager import MultilingualPageManager

        # fix PageManager to inherit from MultilingualManager
        # since automatic manager patching no longer works (Django 1.10 and newer)
        AbstractPage.objects = MultilingualPageManager()
        AbstractPage.objects.contribute_to_class(AbstractPage, 'objects')
        Page.objects = MultilingualPageManager()
        Page.objects.contribute_to_class(Page, 'objects')

        page_patch = import_module('wagtail_translation.page_patch')
        site_patch = import_module('wagtail_translation.site_patch')
        query_patch = import_module('wagtail_translation.query_patch')
        views_patch = import_module('wagtail_translation.views_patch')

        for name in page_patch.__all__:
            setattr(Page, name, getattr(page_patch, name))
        for name in site_patch.__all__:
            setattr(Site, name, getattr(site_patch, name))
        for name in query_patch.__all__:
            setattr(PageQuerySet, name, getattr(query_patch, name))
        for name in views_patch.__all__:
            setattr(pages, name, getattr(views_patch, name))

        import wagtail_translation.signal_handlers
