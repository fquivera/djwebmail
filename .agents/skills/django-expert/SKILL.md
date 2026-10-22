---
name: django-expert
description: Expert Django backend development guidance. Use when creating Django models, views, serializers, or APIs; debugging ORM queries or migrations; optimizing database performance; implementing authentication; writing tests; or working with Django REST Framework. Follows Django best practices and modern patterns.
---

# Django Expert

## Overview

This skill provides expert guidance for Django backend development with comprehensive coverage of models, views, Django REST Framework, forms, authentication, testing, and performance optimization. It follows official Django best practices and modern Python conventions to help you build robust, maintainable applications.

**Key Capabilities:**
- Model design with optimal ORM patterns
- View implementation (FBV, CBV, DRF viewsets)
- Django REST Framework API development
- Query optimization and performance tuning
- Authentication and permissions
- Testing strategies and patterns
- Security best practices

## When to Use

Invoke this skill when you encounter these triggers:

**Model & Database Work:**
- "Create a Django model for..."
- "Optimize this queryset/database query"
- "Generate migrations for..."
- "Design database schema for..."
- "Fix N+1 query problem"

**View & API Development:**
- "Create an API endpoint for..."
- "Build a Django view that..."
- "Implement DRF serializer/viewset"
- "Add filtering/pagination to API"

**Authentication & Security:**
- "Implement authentication/permissions"
- "Create custom user model"
- "Secure this endpoint/view"

**Testing & Quality:**
- "Write tests for this Django app"
- "Debug this Django error/issue"
- "Review Django code for issues"

**Performance & Optimization:**
- "This Django view is slow"
- "Optimize database queries"
- "Add caching to..."

**Production Deployment:**
- "Deploy Django to production"
- "Configure Django for production"
- "Set up HTTPS/SSL for Django"
- "Production settings checklist"
- "Configure production database/cache"

## Instructions

Follow this workflow when handling Django development requests:

### 1. Analyze the Request and Gather Context

**Identify the task type:**
- Model design (database schema, relationships, migrations)
- View/API development (FBV, CBV, DRF viewsets, serializers)
- Query optimization (N+1 problems, database performance)
- Authentication/permissions (user models, access control)
- Testing (unit tests, integration tests, fixtures)
- Security review (CSRF, XSS, SQL injection, permissions)
- Production deployment (settings, HTTPS, database, caching, monitoring)
- Template rendering (Django templates, context processors)

**Leverage available context:**
- Read relevant existing code and project conventions first
- Check Django version for compatibility considerations
- Inspect `config/settings/` and `apps/` to match the existing layout

### 2. Load Relevant Reference Documentation

Based on the task type, reference the appropriate bundled documentation:

- **Models/ORM work** -> `references/models-and-orm.md`
  - Model design patterns and field choices
  - Relationship configurations (ForeignKey, ManyToMany)
  - Custom managers and QuerySet methods
  - Migration strategies

- **View/API development** -> `references/views-and-urls.md` + `references/drf-guidelines.md`
  - FBV vs CBV decision criteria
  - DRF serializers, viewsets, and routers
  - URL configuration patterns
  - Middleware and request/response handling

- **Performance issues** -> `references/performance-optimization.md`
  - Query optimization techniques (select_related, prefetch_related)
  - Caching strategies (Redis, Memcached, database caching)
  - Database indexing and query profiling
  - Connection pooling and async patterns

- **Production deployment** -> `references/production-deployment.md`
  - Critical settings (DEBUG, SECRET_KEY, ALLOWED_HOSTS)
  - HTTPS and SSL/TLS configuration
  - Database and cache configuration
  - Static/media file serving
  - Error monitoring and logging
  - Deployment process and health checks

- **Security concerns** -> `references/security-checklist.md`
  - CSRF/XSS/SQL injection prevention
  - Authentication and authorization patterns
  - Secure configuration practices
  - Input validation and sanitization

- **Testing tasks** -> `references/testing-strategies.md` plus the
  **pytest-django-patterns** skill (canonical for pytest + factories)
  - Test structure and organization
  - Fixtures and factories
  - Mocking external dependencies
  - Coverage and CI/CD integration

- **Template rendering** -> **django-templates** skill, then
  **htmx-patterns** / **htmx-alpine** when the page is interactive
  - Inheritance, partials, custom tags and filters

### 3. Implement Following Django Best Practices

**Code quality standards:**
- Follow PEP 8 and Django coding style
- Use Django built-ins over third-party packages when possible
- Keep views thin; place row-level rules in models and use-case orchestration in services
  (canonical boundary: `django-models`)
- Write descriptive variable names and add docstrings for complex logic
- Handle errors gracefully with appropriate exceptions

**Django-specific patterns:**
- Use `select_related()` for FK/OneToOne, `prefetch_related()` for reverse FK/M2M
- Leverage class-based views and mixins for code reuse
- Use Django forms/serializers for validation
- Follow Django's migration workflow (never edit applied migrations)
- Use Django's built-in security features (CSRF tokens, auth decorators)

**API development (DRF):**
- Use ModelSerializer for standard CRUD operations
- Implement proper pagination and filtering
- Use appropriate permission classes
- Follow RESTful conventions for endpoints
- Version APIs when making breaking changes

### 4. Validate and Test

Before presenting the solution:

**Code review:**
- Check for N+1 query problems (use Django Debug Toolbar mentally)
- Verify proper error handling and edge cases
- Ensure security best practices are followed
- Confirm migrations are clean and reversible

**Testing considerations:**
- Suggest or write appropriate tests for new functionality
- Verify test coverage for critical paths
- Check that fixtures/factories are maintainable

**Performance check:**
- Review database queries for efficiency
- Consider caching opportunities
- Verify proper use of database indexes

## Bundled Resources

**references/** - Detailed Django documentation, loaded only when needed.

| File | Size | Focus |
|---|---|---|
| `references/models-and-orm.md` | ~1.3k words | Fields, relationships, QuerySets, migrations, SQL safety |
| `references/views-and-urls.md` | ~1.6k words | FBV vs CBV, mixins, routing, middleware, status codes |
| `references/drf-guidelines.md` | ~1.5k words | Serializers, viewsets, pagination, filtering, permissions |
| `references/testing-strategies.md` | ~3.6k words | TestCase vs pytest, fixtures, mocking, coverage, CI |
| `references/security-checklist.md` | ~1.3k words | CSRF, XSS, SQL injection, auth, secrets, headers |
| `references/performance-optimization.md` | ~1.4k words | Query tuning, indexes, caching, pooling, async |
| `references/production-deployment.md` | ~2.2k words | Settings, HTTPS, static/media, email, monitoring, zero-downtime |
| `references/examples.md` | ~1.0k words | End-to-end model, query, API, and test examples |

## Integration with Other Skills

Prefer these focused skills over duplicating their content:

- **django-models** - model design, QuerySets, model/service boundary (canonical)
- **django-forms** - forms, validation, HTMX submission
- **django-templates** - template inheritance, partials, tags
- **django-patterns** - architecture, services, DRF, caching, middleware
- **django-infrastructure** - layout, settings split, Docker, requirements
- **htmx-patterns** / **htmx-alpine** - interactive UI
- **pytest-django-patterns** - pytest, factories, TDD
- **celery-patterns** - background tasks
- **django-extensions** - project introspection commands
- **systematic-debugging** - root-cause methodology

## Additional Notes

**Django Version Compatibility:**
- Target the current LTS (5.2) for production; 4.2 LTS is end-of-life
- Check deprecation warnings when upgrading to a new feature release
- Use `django-upgrade` for automated migration of syntax changes

**Common Pitfalls to Avoid:**
- Circular imports (use lazy references)
- Missing `related_name` on relationships
- Forgetting database indexes on frequently queried fields
- Using `get()` without exception handling
- N+1 queries in templates and serializers
