import { randomBytes } from "node:crypto";
import { buildContentSecurityPolicy } from "./contentSecurityPolicy";

export interface HtmlBuilderOptions {
    title: string;
    cspSource?: string;
    styles?: string;
    scripts?: Array<{ type?: string; src: string }>;
    body: string;
}

export function buildHtml(options: HtmlBuilderOptions): string {
    const nonce = randomBytes(18).toString("base64");
    const policy = buildContentSecurityPolicy(options.cspSource ?? "", nonce);
    const scriptTags = options.scripts
        ?.map(script => {
            const type = script.type ? ` type="${script.type}"` : '';
            return `<script nonce="${nonce}"${type} src="${script.src}"></script>`;
        })
        .join('\n        ') || '';

    return /* html */ `
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1.0" />
            <meta http-equiv="Content-Security-Policy" content="${policy}" />
            <title>${options.title}</title>
            ${scriptTags ? scriptTags + '\n            ' : ''}<style nonce="${nonce}">
                html, body {
                    padding: 0;
                    margin: 0;
                    height: 100%;
                    width: 100%;
                    overflow: hidden;
                }
                ${options.styles || ''}
            </style>
        </head>
        <body>
            ${options.body}
        </body>
        </html>`;
}
