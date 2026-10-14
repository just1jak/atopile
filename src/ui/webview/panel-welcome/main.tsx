import React from "react";
import { render, logoUrl } from "../common/render";
import { rpcClient } from "../common/webviewRpcClient";
import { localAgent, localAgentCommand, localProviderLabel, localModelLabel } from "../common/localAgent";
import "./welcome.css";

function openExternal(url: string) {
  rpcClient?.sendAction("vscode.openExternal", { url });
}

function ExternalLink({
  href,
  className,
  children,
}: {
  href: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <a
      className={className}
      onClick={(e) => {
        e.preventDefault();
        openExternal(href);
      }}
    >
      {children}
    </a>
  );
}

function App() {
  return (
    <>

      <div className="hero">
        <img className="hero-logo" src={logoUrl} alt="atopile" />
        <h1>Welcome to Atopile Local</h1>
        <p className="tagline">Design electronics with code</p>
      </div>

      <div className="content">
        <h2>Getting started</h2>
        <div className="steps">
          <Step num={1} title="Explore the editor">
            Open your project folder and select its build target in the sidebar. Your files are saved on your computer.
          </Step>
          <Step num={2} title="See the layout">
            Build the circuit, then inspect its layout, nets, pinout, and 3D model from the sidebar tools.
          </Step>
          <Step num={3} title="Try something">
            Use your own AI provider or local endpoint to edit circuits and run builds. Imported component assets can stay local.
          </Step>
        </div>

        <h2>Learn more</h2>
        <div className="docs-links">
          <ExternalLink className="docs-link" href="https://docs.atopile.io">
            <div className="docs-link-icon">&#128218;</div>
            <div className="docs-link-label">Documentation</div>
          </ExternalLink>
          <ExternalLink
            className="docs-link"
            href="https://github.com/atopile/atopile"
          >
            <div className="docs-link-icon">&#128187;</div>
            <div className="docs-link-label">Source code</div>
          </ExternalLink>
          <ExternalLink
            className="docs-link"
            href="https://discord.gg/nr5V3cVPBb"
          >
            <div className="docs-link-icon">&#128172;</div>
            <div className="docs-link-label">Community</div>
          </ExternalLink>
        </div>

        <div className="cta-card">
          <h3>Configure your AI</h3>
          <p>
            Provider: {localProviderLabel()} · Model: {localModelLabel()}.
            <br />
            Part catalogs and DeepPCB autolayout remain external services.
          </p>
          <button className="cta-btn" type="button" onClick={() => localAgentCommand("openAgentSettings")}>AI settings</button>
          <button className="cta-btn" type="button" onClick={() => localAgentCommand("connectChatGPT")}>{localAgent?.chatgptConnected ? "Check ChatGPT connection" : "Connect ChatGPT"}</button>
        </div>
      </div>
    </>
  );
}

function Step({
  num,
  title,
  children,
}: {
  num: number;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="step">
      <div className="step-num">{num}</div>
      <div className="step-text">
        <div className="step-title">{title}</div>
        <div className="step-desc">{children}</div>
      </div>
    </div>
  );
}

render(App);
