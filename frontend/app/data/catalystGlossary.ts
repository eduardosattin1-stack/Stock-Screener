// Back-compat shim. The canonical copy source of truth is now ./voice.ts
// (VOICE map + termLabel/<Term>). GLOSSARY is derived there from every VOICE
// entry that carries a definition; Tip.tsx still imports it from here. Add new
// terms to voice.ts, not here.
export { GLOSSARY } from "./voice";
