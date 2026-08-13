"""Home for individual prompt template *definition* modules (a future sprint).

This package is never scanned automatically — `app.prompts.registry.PromptRegistry`
only ever learns about a template when something explicitly calls
`register(PromptTemplate(...))` (see that module's docstring: "No
filesystem scanning. Templates are registered explicitly."). A future
sprint adding a concrete template (e.g. "company_research") would define
its `PromptTemplate` constant in a module here and have some
composition-root code import and register it explicitly. This sprint adds
no concrete templates — only the framework itself.
"""
