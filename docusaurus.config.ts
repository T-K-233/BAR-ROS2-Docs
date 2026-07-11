import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

// https://docusaurus.io/docs/api/docusaurus-config
const config: Config = {
  title: 'Humanoid Control',
  tagline: 'Humanoid Control low-level control stack',
  favicon: 'img/logo.svg',

  // Production URL for GitHub Pages project site.
  url: 'https://berkeley-humanoids.github.io',
  baseUrl: '/Humanoid-Control-Website/',

  organizationName: 'Berkeley-Humanoids',
  projectName: 'Humanoid-Control-Website',
  trailingSlash: false,

  // Fail the build on broken internal links — same policy as VitePress.
  onBrokenLinks: 'throw',
  onBrokenMarkdownLinks: 'throw',

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          editUrl:
            'https://github.com/Berkeley-Humanoids/Humanoid-Control-Website/tree/main/',
          routeBasePath: '/',
          showLastUpdateTime: true,
          showLastUpdateAuthor: true,
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    image: 'img/logo.svg',
    colorMode: {
      defaultMode: 'light',
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: 'Humanoid Control',
      logo: {
        alt: 'Humanoid Control logo',
        src: 'img/logo.svg',
      },
      items: [
        {to: '/getting_started/intro', label: 'Getting started', position: 'left'},
        {to: '/tutorials/',            label: 'Tutorials',       position: 'left'},
        {to: '/how_to/',               label: 'How-to',          position: 'left'},
        {to: '/concepts/',             label: 'Concepts',        position: 'left'},
        {to: '/reference/packages',    label: 'Reference',       position: 'left'},
        {
          href: 'https://github.com/Berkeley-Humanoids/humanoid_control_ros2',
          label: 'GitHub',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'light',
      links: [
        {
          title: 'Getting started',
          items: [
            {label: 'Introduction',  to: '/getting_started/intro'},
            {label: 'Installation',  to: '/getting_started/installation'},
            {label: 'Lite 101',      to: '/getting_started/lite_101'},
          ],
        },
        {
          title: 'Learn',
          items: [
            {label: 'Tutorials',     to: '/tutorials/'},
            {label: 'How-to guides', to: '/how_to/'},
            {label: 'Concepts',      to: '/concepts/'},
          ],
        },
        {
          title: 'Reference',
          items: [
            {label: 'Hardware specs',  to: '/reference/hardware_specs'},
            {label: 'Packages',        to: '/reference/packages'},
            {label: 'Controllers',     to: '/reference/controllers'},
            {label: 'Launch args',     to: '/reference/launch_args'},
          ],
        },
        {
          title: 'Project',
          items: [
            {
              label: 'Humanoid Control on GitHub',
              href: 'https://github.com/Berkeley-Humanoids/humanoid_control_ros2',
            },
            {
              label: 'Berkeley Humanoids',
              href: 'https://github.com/Berkeley-Humanoids',
            },
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} Humanoid Control Dev. Built with Docusaurus. BSD-3-Clause.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['bash', 'yaml', 'cmake', 'cpp', 'python', 'xml-doc', 'json'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
