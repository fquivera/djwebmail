---
name: htmx-patterns
description: HTMX patterns for Django including partial templates, hx-* attributes, and dynamic UI without JavaScript. Use when building interactive UI, handling AJAX requests, or creating dynamic components.
---

# HTMX Patterns for Django

Django-specific conventions for HTMX. The framework-agnostic interaction model
and Alpine.js rules live in the **htmx-alpine** skill; do not duplicate them here.

## Core Philosophy

- Server renders HTML, not JSON - HTMX requests return HTML fragments, not data
- Partial templates for dynamic updates - separate `_partial.html` files for HTMX responses
- Progressive enhancement - pages work without JavaScript, HTMX enhances UX
- Minimal client-side complexity - let the server do the heavy lifting

## Critical Hints & Reminders

### UX Best Practices

**Always include loading indicators**
- Use `hx-indicator` to show loading states during requests
- Users should never wonder if their action worked
- Example: `<button hx-get="/data/" hx-indicator="#spinner">Load</button>`

**Always provide user feedback**
- Prefer an out-of-band toast partial triggered with `HX-Trigger` over the messages framework
- Django messages only render on the next full page load, so they are invisible after an HTMX swap
- Return error messages inside the HTMX response, never a silent 200

**Handle errors gracefully**
- Re-render the form with errors and status **200** so HTMX swaps it (HTMX ignores 4xx by default)
- Use 400 for malformed requests, 403 for authorization failures, 500 for server errors
- Only use 422 if `htmx.config.responseHandling` is configured to swap it
- Don't swallow exceptions - log and show user-friendly messages

### Django-Specific Patterns

**Always detect HTMX requests**
- Check `request.headers.get("HX-Request")` to detect HTMX requests
- Return partial templates for HTMX, full page templates otherwise
- Pattern: `if request.headers.get("HX-Request"): return render(request, "_partial.html", context)`

**Always return partials for HTMX**
- HTMX requests should return `_partial.html` templates, not full pages with `base.html`
- Full page responses to HTMX requests break the UX and send duplicate HTML
- Partials should be self-contained HTML fragments

**Always validate request.method**
- Check `request.method == "POST"` before processing form data
- Return proper status codes (405 Method Not Allowed for wrong methods)

**CSRF must be configured once in the base template**
- Put `hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'` on a stable ancestor (usually `<body>`)
- Verify it renders a non-empty token; without it every `hx-post` fails with 403
- Individual forms do not need extra hidden CSRF inputs for HTMX requests
- If you cache pages, remember the token is per-session: never cache HTML containing it

### Template Organization

**Naming convention**
- Partials: `_partial.html` (underscore prefix)
- Full pages: `list.html`, `detail.html`, `form.html` (no prefix)
- Example: `mail/list.html` (full page) includes `mail/_message_list.html` (partial)

**Structure**
- Full page template extends `base.html` and includes partial
- Partial contains only the dynamic HTML fragment
- HTMX targets the partial's container div

**Keep partials focused**
- Each partial should represent one logical UI component
- Avoid partials that are too large or do too much
- Compose larger UIs from multiple smaller partials

## Django View Patterns

### HTMX Detection

Check the `HX-Request` header to detect HTMX requests:

```python
from django.views.decorators.vary import vary_on_headers

@vary_on_headers("HX-Request")
def my_view(request):
    context = {...}

    if request.headers.get("HX-Request"):
        return render(request, "app/_partial.html", context)

    return render(request, "app/full_page.html", context)
```

`vary_on_headers` is required whenever the response changes on `HX-Request`;
otherwise a shared cache can serve a fragment as a full page (or the reverse).

### Form Handling Pattern

Key points:
- Validate form normally
- On success: return partial with new data OR trigger client-side event
- On error: return partial with form errors
- Always handle both HTMX and non-HTMX cases

```python
from django.shortcuts import redirect, render

def create_view(request):
    if request.method == "POST":
        form = MyForm(request.POST)
        if form.is_valid():
            obj = form.save()
            if request.headers.get("HX-Request"):
                return render(request, "app/_item.html", {"item": obj})
            return redirect("app:list")

        # Invalid: re-render the partial. Keep 200 so HTMX swaps the form.
        if request.headers.get("HX-Request"):
            return render(request, "app/_form.html", {"form": form})
    else:
        form = MyForm()

    return render(request, "app/create.html", {"form": form})
```

## Response Headers Reference

HTMX respects special response headers for client-side behavior:

### HX-Trigger
Trigger client-side events after response
- Use case: Update other parts of page after action
- Plain event: `response["HX-Trigger"] = "itemCreated"`
- With detail payload (needed for toasts): `response["HX-Trigger"] = json.dumps({"showToast": {"level": "success", "message": "Saved"}})`
- Template listens: `<div hx-get="/count/" hx-trigger="itemCreated from:body">`

### HX-Redirect
Client-side redirect
- Use case: Redirect after successful action
- Example: `response["HX-Redirect"] = reverse("app:detail", args=[obj.pk])`

### HX-Retarget / HX-Reswap
Override hx-target and hx-swap from server
- Use case: Different targets for success vs error
- Success: `response["HX-Retarget"] = "#main"`
- Error: Return partial without changing target (targets the form)

### HX-Refresh
Force full page refresh
- Use case: Major state change that affects whole page
- Example: `response["HX-Refresh"] = "true"`

## Common Pitfalls

- **Missing loading indicators**: Always use `hx-indicator` - users click multiple times without feedback
- **Full pages in HTMX responses**: Return `_partial.html`, not full pages with `base.html` - check `HX-Request` header
- **Not handling form errors**: Always return the form with errors on validation failure, not just the success case
- **Not disabling buttons**: Use `hx-disabled-elt="this"` to prevent duplicate submissions
- **N+1 queries**: HTMX views need `select_related()`/`prefetch_related()` just like regular views

## Integration with Other Skills

- **htmx-alpine**: Interaction model, Alpine.js state, accessibility, SSE/WebSocket
- **django-templates**: Partial template organization and inheritance patterns
- **django-forms**: HTMX form submission and validation
- **django-extensions**: Use `show_urls` to verify HTMX endpoints
- **pytest-django-patterns**: Testing HTMX endpoints and headers
- **systematic-debugging**: Debug HTMX request/response issues
