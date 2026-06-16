export const isAuthDisabled =
  import.meta.env.DEV || import.meta.env.VITE_DISABLE_AUTH === "true";
