import type { VariantProps } from "class-variance-authority"
import { cva } from "class-variance-authority"

export { default as Button } from "./Button.vue"

export const buttonVariants = cva(
  'group/button inline-flex shrink-0 items-center justify-center whitespace-nowrap rounded-lg border border-transparent bg-clip-padding text-sm font-semibold outline-none select-none transition-[color,background-color,border-color,box-shadow,transform] duration-150 ease-out focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/25 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 active:not-aria-[haspopup]:translate-y-px disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*=size-])]:size-4',
  {
    variants: {
      variant: {
        default: 'bg-primary text-primary-foreground shadow-[0_1px_2px_rgba(15,23,42,0.12),0_8px_18px_-14px_rgba(13,148,136,0.85)] hover:bg-primary/90 hover:shadow-[0_2px_4px_rgba(15,23,42,0.12),0_12px_24px_-16px_rgba(13,148,136,0.8)]',
        outline: 'border-border/90 bg-white/90 text-foreground shadow-[0_1px_2px_rgba(15,23,42,0.04)] hover:border-primary/25 hover:bg-accent/65 hover:text-accent-foreground aria-expanded:bg-accent aria-expanded:text-accent-foreground',
        secondary: 'border-border/60 bg-secondary text-secondary-foreground hover:bg-secondary/75 aria-expanded:bg-secondary aria-expanded:text-secondary-foreground',
        soft: 'border-primary/10 bg-primary/10 text-primary shadow-[inset_0_0_0_1px_rgba(255,255,255,0.35)] hover:border-primary/20 hover:bg-primary/15',
        ghost: 'text-muted-foreground hover:bg-muted/80 hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground',
        destructive: 'border-destructive/10 bg-destructive/10 text-destructive hover:border-destructive/20 hover:bg-destructive/15 focus-visible:border-destructive/40 focus-visible:ring-destructive/20',
        link: 'text-primary underline-offset-4 hover:underline',
      },
      size: {
        "default": 'h-9 gap-2 px-4 has-data-[icon=inline-end]:pr-3 has-data-[icon=inline-start]:pl-3',
        "xs": 'h-7 gap-1 rounded-md px-2 text-xs [&_svg:not([class*=size-])]:size-3',
        "sm": 'h-8 gap-1.5 px-3 text-[0.8rem] [&_svg:not([class*=size-])]:size-3.5',
        "lg": 'h-10 gap-2 px-5',
        "icon": 'size-9',
        "icon-xs": 'size-7 rounded-md [&_svg:not([class*=size-])]:size-3',
        "icon-sm": 'size-8',
        "icon-lg": 'size-10',
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
)
export type ButtonVariants = VariantProps<typeof buttonVariants>
