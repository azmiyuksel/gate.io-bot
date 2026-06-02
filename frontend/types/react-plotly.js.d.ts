// Minimal type shim: react-plotly.js ships no bundled declarations.
declare module "react-plotly.js" {
  import type { Component } from "react";
  import type { Data, Layout, Config } from "plotly.js";

  export interface PlotParams {
    data?: Data[];
    layout?: Partial<Layout>;
    config?: Partial<Config>;
    style?: React.CSSProperties;
    className?: string;
    useResizeHandler?: boolean;
    [key: string]: unknown;
  }

  export default class Plot extends Component<PlotParams> {}
}
