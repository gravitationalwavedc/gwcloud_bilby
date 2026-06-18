# bilbyui static assets

Django serves these files as `{% static 'bilbyui/...' %}`. The htmx UI loads
`app.css`, `htmx.min.js`, and `alpine.min.js` from here.

## CSS build

| Path | Role |
|------|------|
| `scss/` | SCSS sources (edit these) |
| `scss/app.scss` | Build entry point (`theme.scss` + `styles.scss`) |
| `scss/vendor/bootstrap/` | Vendored Bootstrap 4.6.2 SCSS (compile-time only) |
| `app.css` | Compiled stylesheet served in production/dev |
| `build-css.sh` | Wrapper around the `sass` CLI |

**Prerequisites:** install the Dart Sass CLI once:

```bash
npm install -g sass
```

From the repository root:

```bash
cd src/static/bilbyui
./build-css.sh
```

Or run the compile command directly (requires `sass` on your `PATH`):

```bash
cd src/static/bilbyui
sass scss/app.scss app.css --no-source-map \
  --silence-deprecation=import,if-function,global-builtin,color-functions,abs-percent
```

Commit the updated `app.css` after changing SCSS.

See also the **Styles** subsection in the top-level `README.md`.
