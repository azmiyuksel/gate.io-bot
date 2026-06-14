import * as React from "react";
import { cn } from "@/lib/utils";

const variantClass = {
  primary: "bg-primary text-white shadow-sm hover:brightness-95",
  danger: "bg-danger text-white shadow-sm hover:brightness-95",
  secondary: "bg-transparent text-foreground hover:bg-border/60",
  ghost: "bg-transparent text-muted hover:text-foreground hover:bg-border/40",
} as const;

type ButtonVariant = keyof typeof variantClass;

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(({
  className,
  variant = "primary",
  ...props
}, ref) => {
  return (
    <button
      ref={ref}
      className={cn(
        "inline-flex h-10 items-center justify-center gap-2 rounded-md px-4 text-sm font-medium transition focus:outline-none focus:ring-2 focus:ring-primary/30 focus:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-50",
        variantClass[variant],
        className,
      )}
      {...props}
    />
  );
});
Button.displayName = "Button";
