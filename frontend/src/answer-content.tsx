import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {answerText} from './answer-text';
/** Render provider Markdown as safe React elements; raw HTML is never inserted. */
export default function AnswerContent({text}:{text:string}){
 return <div className="answer-markdown"><Markdown remarkPlugins={[remarkGfm]} skipHtml components={{
  h1:({children})=><h3>{children}</h3>,h2:({children})=><h3>{children}</h3>,h3:({children})=><h4>{children}</h4>,
  table:({children})=><div className="answer-table-scroll"><table>{children}</table></div>,
  a:({href,children})=><a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
 }}>{answerText(text)}</Markdown></div>;
}
