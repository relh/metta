declare global {
  var cookieStore: {
    get: (name: string) => Promise<{ value: string } | null>;
  };
}

export {};
