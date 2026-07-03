import React from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App.js?v=0.9.0";

const h = React.createElement;

createRoot(document.getElementById("root")).render(h(App));
