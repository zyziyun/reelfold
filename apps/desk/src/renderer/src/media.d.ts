// Bundled audio (Vite turns the import into the hashed asset URL): Settings › Voice samples.
declare module '*.mp3' {
  const src: string;
  export default src;
}
