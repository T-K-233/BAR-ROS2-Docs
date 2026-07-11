import type {ReactNode} from 'react';
import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import Layout from '@theme/Layout';
import Heading from '@theme/Heading';

import styles from './index.module.css';

const GITHUB_URL = 'https://github.com/Berkeley-Humanoids/humanoid_control_ros2';

type Entry = {
  title: string;
  to: string;
  desc: string;
};

const CONTENTS: Entry[] = [
  {
    title: 'Getting started',
    to: '/getting_started/intro',
    desc: 'Install with pixi, then bring up Lite in MuJoCo in about ten minutes — no system-wide ROS install required.',
  },
  {
    title: 'Tutorials',
    to: '/tutorials/',
    desc: 'Learning-oriented walkthroughs: drive a single Robstride, walk an FSM in simulation, run a tracking policy.',
  },
  {
    title: 'How-to guides',
    to: '/how_to/',
    desc: 'Task recipes for real work: first real bringup, calibrate the zero pose, recover from a fault, probe the CAN bus.',
  },
  {
    title: 'Concepts',
    to: '/concepts/',
    desc: 'The reasoning layer: the architecture, the five-mode FSM, the MIT command surface, the safety pipeline.',
  },
  {
    title: 'Reference',
    to: '/reference/quick_reference',
    desc: 'Dense and scannable: hardware specs, packages, controllers, launch args, message schemas, troubleshooting.',
  },
];

function Hero() {
  return (
    <header className={styles.hero}>
      <div className="container">
        <Heading as="h1" className={styles.title}>
          Humanoid Control
        </Heading>
        <p className={styles.tagline}>
          One low-level control stack for two Berkeley bimanual humanoids — Lite and Prime.
        </p>
        <p className={styles.intro}>
          Built on ROS 2 Jazzy and <code>ros2_control</code> under PREEMPT_RT. The same
          controllers, MIT-mode command interfaces, and message schemas run across both
          robots; mock, MuJoCo, and real CAN / EtherCAT hardware are selectable from a
          single <code>xacro</code> argument. Robot differences live entirely in URDF and
          hardware-plugin selection.
        </p>
        <div className={styles.actions}>
          <Link className="button button--primary" to="/getting_started/intro">
            Get started →
          </Link>
          <Link className={styles.ghostLink} href={GITHUB_URL}>
            View on GitHub ↗
          </Link>
        </div>
      </div>
    </header>
  );
}

function Contents() {
  return (
    <section className="container">
      <div className={styles.contents}>
        <Heading as="h2" className={styles.contentsHead}>
          Documentation
        </Heading>
        <div className={styles.list}>
          {CONTENTS.map((item) => (
            <div key={item.to}>
              <Heading as="h3" className={styles.entryTitle}>
                <Link to={item.to}>{item.title}</Link>
              </Heading>
              <p className={styles.entryDesc}>{item.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

export default function Home(): ReactNode {
  const {siteConfig} = useDocusaurusContext();
  return (
    <Layout
      title={`${siteConfig.title} — ${siteConfig.tagline}`}
      description="Docs for Humanoid Control, the unified low-level control stack for the Berkeley bimanual humanoids.">
      <Hero />
      <main>
        <Contents />
      </main>
    </Layout>
  );
}
