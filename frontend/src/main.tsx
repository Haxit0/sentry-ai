import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import SubmissionWorkbench from "./SubmissionWorkbench";
import "./style.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {window.location.pathname.startsWith("/legacy") ? <App /> : <SubmissionWorkbench />}
  </StrictMode>,
);
