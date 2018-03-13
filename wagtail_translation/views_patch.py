from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.utils.translation import ugettext as _

from modeltranslation import settings as mt_settings
from modeltranslation.utils import build_localized_fieldname

from wagtail.admin import messages
from wagtail.admin.utils import (
    user_has_any_page_permission, user_passes_test)
from wagtail.admin.views.pages import get_valid_next_url_from_request
from wagtail.core import hooks
from wagtail.core.models import Page

from .forms import CopyForm

__all__ = ['copy', ]


@user_passes_test(user_has_any_page_permission)
def copy(request, page_id):
    page = Page.objects.get(id=page_id)

    # Parent page defaults to parent of source page
    parent_page = page.get_parent()

    # Check if the user has permission to publish subpages on the parent
    can_publish = parent_page.permissions_for_user(request.user).can_publish_subpage()

    # Create the form
    form = CopyForm(request.POST or None, user=request.user, page=page, can_publish=can_publish)

    next_url = get_valid_next_url_from_request(request)

    for fn in hooks.get_hooks('before_copy_page'):
        result = fn(request, page)
        if hasattr(result, 'status_code'):
            return result

    # Check if user is submitting
    if request.method == 'POST':
        # Prefill parent_page in case the form is invalid (as prepopulated value for the form field,
        # because ModelChoiceField seems to not fall back to the user given value)
        parent_page = Page.objects.get(id=request.POST['new_parent_page'])

        if form.is_valid():
            # Receive the parent page (this should never be empty)
            if form.cleaned_data['new_parent_page']:
                parent_page = form.cleaned_data['new_parent_page']

            if not page.permissions_for_user(request.user).can_copy_to(
                    parent_page,
                    form.cleaned_data.get('copy_subpages')):
                raise PermissionDenied

            # Re-check if the user has permission to publish subpages on the new parent
            can_publish = parent_page.permissions_for_user(request.user).can_publish_subpage()

            # build translated attrs
            translated_attrs = {}
            for lang in mt_settings.AVAILABLE_LANGUAGES:
                new_title_field = build_localized_fieldname("new_title", lang)
                if form.cleaned_data.get(new_title_field):
                    title_field = build_localized_fieldname("title", lang)
                    new_slug_field = build_localized_fieldname("new_slug", lang)
                    slug_field = build_localized_fieldname("slug", lang)
                    translated_attrs.update({
                        '{}'.format(title_field): form.cleaned_data[new_title_field],
                        '{}'.format(slug_field): form.cleaned_data[new_slug_field],
                    })

            # Copy the page
            new_page = page.copy(
                recursive=form.cleaned_data.get('copy_subpages'),
                to=parent_page,
                update_attrs=translated_attrs,
                keep_live=(can_publish and form.cleaned_data.get('publish_copies')),
                user=request.user,
            )

            # Give a success message back to the user
            if form.cleaned_data.get('copy_subpages'):
                messages.success(
                    request,
                    _("Page '{0}' and {1} subpages copied.").format(
                        page.get_admin_display_title(),
                        new_page.get_descendants().count())
                )
            else:
                messages.success(request, _("Page '{0}' copied.").format(
                    page.get_admin_display_title()))

            for fn in hooks.get_hooks('after_copy_page'):
                result = fn(request, page, new_page)
                if hasattr(result, 'status_code'):
                    return result

            # Redirect to explore of parent page
            if next_url:
                return redirect(next_url)
            return redirect('wagtailadmin_explore', parent_page.id)

    return render(request, 'wagtailadmin/pages/copy.html', {
        'page': page,
        'form': form,
        'next': next_url,
    })
