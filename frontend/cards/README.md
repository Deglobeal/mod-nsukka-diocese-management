# Frontend Cards

This package organizes Python presentation models for cards and related
display elements used by the Django-rendered frontend.

## Directory structure

- `models/shared/`: reusable card presentation models and actions.
- `models/types/`: shared card variants and semantic statuses.
- `pages/<page>/models/`: page-specific presentation models.

## Architectural boundaries

- `frontend/cards/` defines presentation data, not database structures.
- `templates/` contains HTML and Django templates.
- `static/css/` contains stylesheets.
- `static/css/tokens/` is the source of truth for global design tokens,
  including colors, spacing, borders, shadows, and transitions.
- `apps/` retains Django application responsibilities, including database
  models, forms, views, permissions, and business logic.

Presentation models must not duplicate Django ORM models or take ownership
of backend business rules.

Page-specific presentation models should describe what the frontend needs
to display. Views remain responsible for preparing the context, while
templates remain responsible for rendering the HTML.

New page integrations should be introduced incrementally and tested without
unnecessary changes to existing templates, CSS, or backend behavior.
