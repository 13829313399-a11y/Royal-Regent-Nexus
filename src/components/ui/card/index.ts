import type { VariantProps } from 'class-variance-authority'
import { cva } from 'class-variance-authority'

export { default as Card } from './Card.vue'
export { default as CardAction } from './CardAction.vue'
export { default as CardContent } from './CardContent.vue'
export { default as CardDescription } from './CardDescription.vue'
export { default as CardFooter } from './CardFooter.vue'
export { default as CardHeader } from './CardHeader.vue'
export { default as CardTitle } from './CardTitle.vue'

export const cardVariants = cva(
  'flex flex-col text-card-foreground',
  {
    variants: {
      variant: {
        default: 'surface-l1 rounded-2xl',
        subtle: 'rounded-xl border border-border/75 bg-muted/45',
        interactive:
          'surface-l1 rounded-2xl cursor-pointer transition-[transform,border-color,box-shadow] duration-[var(--motion-duration-base)] ease-spring-smooth hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-elevation-2 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/25 active:scale-[0.99]',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
)

export type CardVariants = VariantProps<typeof cardVariants>
