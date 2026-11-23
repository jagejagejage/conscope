import type { ReactNode, SVGProps } from "react";

type IconName = "grid" | "search" | "ticket" | "settings" | "calendar" | "pin" | "clock" | "arrow" | "pause" | "play" | "edit" | "trash" | "check" | "bell" | "mail" | "chevron" | "close" | "spark" | "info" | "menu" | "minus" | "plus";

const paths: Record<IconName, ReactNode> = {
  grid: <><rect x="3.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.5"/></>,
  search: <><circle cx="10.8" cy="10.8" r="6.8"/><path d="m16 16 4.5 4.5"/></>,
  ticket: <><path d="M4 6.5A2.5 2.5 0 0 0 4 11.5v1A2.5 2.5 0 0 0 4 17.5h16a2.5 2.5 0 0 0 0-5v-1a2.5 2.5 0 0 0 0-5H4Z"/><path d="M13.5 7.5v1m0 3v1m0 3v1"/></>,
  settings: <><circle cx="12" cy="12" r="3"/><path d="m19.4 15 .1.1a1.8 1.8 0 1 1-2.5 2.5l-.1-.1a1.8 1.8 0 0 0-3.1 1.3v.2a1.8 1.8 0 1 1-3.6 0v-.2a1.8 1.8 0 0 0-3.1-1.3l-.1.1a1.8 1.8 0 1 1-2.5-2.5l.1-.1A1.8 1.8 0 0 0 3.3 12H3a1.8 1.8 0 1 1 0-3.6h.2a1.8 1.8 0 0 0 1.3-3.1l-.1-.1a1.8 1.8 0 1 1 2.5-2.5l.1.1A1.8 1.8 0 0 0 10.1 1.5v-.2a1.8 1.8 0 1 1 3.6 0v.2a1.8 1.8 0 0 0 3.1 1.3l.1-.1a1.8 1.8 0 1 1 2.5 2.5l-.1.1a1.8 1.8 0 0 0 1.3 3.1h.2a1.8 1.8 0 1 1 0 3.6h-.2a1.8 1.8 0 0 0-1.3 3.1Z" transform="translate(1 2) scale(.83)"/></>,
  calendar: <><rect x="3.5" y="5" width="17" height="16" rx="2"/><path d="M7.5 3v4m9-4v4M4 9.5h16"/></>,
  pin: <><path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0Z"/><circle cx="12" cy="10" r="2"/></>,
  clock: <><circle cx="12" cy="12" r="8.5"/><path d="M12 7v5l3.5 2"/></>,
  arrow: <><path d="M5 12h14m-6-6 6 6-6 6"/></>,
  pause: <><path d="M8 5v14m8-14v14"/></>,
  play: <path d="m8 5 11 7-11 7V5Z"/>,
  edit: <><path d="m14 5 5 5M4 20l4.5-1 10.8-10.8a2.1 2.1 0 0 0-3-3L5.5 16 4 20Z"/><path d="M12 20h8"/></>,
  trash: <><path d="M4 7h16M10 11v6m4-6v6M6 7l1 13h10l1-13M9 7V4h6v3"/></>,
  check: <path d="m5 12 4.5 4.5L19 7"/>,
  bell: <><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9m-8 12a2 2 0 0 0 4 0"/></>,
  mail: <><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m4 7 8 6 8-6"/></>,
  chevron: <path d="m8 10 4 4 4-4"/>,
  close: <><path d="m6 6 12 12M18 6 6 18"/></>,
  spark: <><path d="m12 3 1.4 5.6L19 10l-5.6 1.4L12 17l-1.4-5.6L5 10l5.6-1.4L12 3Z"/><path d="m19 16 .7 2.3L22 19l-2.3.7L19 22l-.7-2.3L16 19l2.3-.7L19 16Z"/></>,
  info: <><circle cx="12" cy="12" r="9"/><path d="M12 11v5m0-8h.01"/></>,
  menu: <><path d="M4 7h16M4 12h16M4 17h16"/></>,
  minus: <path d="M5 12h14"/>,
  plus: <><path d="M12 5v14m-7-7h14"/></>,
};

export function Icon({ name, size = 20, ...props }: SVGProps<SVGSVGElement> & { name: IconName; size?: number }) {
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      {paths[name]}
    </svg>
  );
}

export type { IconName };
