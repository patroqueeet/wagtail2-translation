import json
import re

from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.utils.translation import get_language

from modeltranslation.utils import build_localized_fieldname
from wagtail.wagtailcore.models import PageRevision


from .page_patch import PREFIX


@receiver(pre_save, sender=PageRevision)
def pre_save_signal_handler(sender, instance, *args, **kwargs):
    content = json.loads(instance.content_json)
    lang_code = get_language()
    title_field = build_localized_fieldname('title', lang_code)
    slug_field = build_localized_fieldname('slug', lang_code)
    url_path_field = build_localized_fieldname('url_path', lang_code)
    xp = re.compile(r"{}[0-9a-f]+".format(PREFIX))
    field_list = [title_field, slug_field, url_path_field,
                  'title', 'slug', 'url_path']
    for field in field_list:
        content[field] = xp.sub("", content[field])
    instance.content_json = json.dumps(content)
