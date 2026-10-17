/** Keep technical citations in evidence panels, including for existing chat history. */
export function answerText(text:string):string {
 const reference=String.raw`(?:Q\d+|T\d+\s*:\s*(?:R|T)?\d+(?:\s*[-–]\s*(?:T\d+\s*:\s*)?(?:R|T)?\d+)?)`;
 return text
  .replace(new RegExp(String.raw`[\[(]\s*${reference}(?:\s*[,;]\s*${reference})*\s*[\])]`,'gi'),'')
  .replace(new RegExp(String.raw`\bT\d+\s*:\s*(?:R|T)?\d+(?:\s*[-–]\s*(?:T\d+\s*:\s*)?(?:R|T)?\d+)?\b`,'gi'),'')
  .replace(/(?<=\S)[ \t]{2,}/g,' ').replace(/ +([.,;!?])/g,'$1').replace(/ +$/gm,'').trim();
}
