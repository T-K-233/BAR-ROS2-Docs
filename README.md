# Humanoid-Control-Website

Documentation site for [Humanoid Control](https://github.com/Berkeley-Humanoids/humanoid_control_ros2),
the Berkeley Humanoids low-level control stack. Built with [Docusaurus 3](https://docusaurus.io/).

## Develop

```sh
npm install
npm start          # http://localhost:3000, hot reload
```

## Build

```sh
npm run build      # static site -> build/
npm run serve      # preview the build locally
```

## Deploy

Pushing to `main` builds and publishes to GitHub Pages via
[`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) — no manual step.

## Authoring

- Docs live in `docs/`; the sidebar order is set in `sidebars.ts`.
- Cross-link with relative paths — Docusaurus drops the `.md` at build.
- Admonitions use Docusaurus 3 syntax: `:::tip[Title]`.
- Diagrams are static SVGs in `static/img/diagrams/`, referenced as `/img/diagrams/…`.
