import {
  createCliRenderer,
  TextRenderable,
  BoxRenderable,
  InputRenderable,
  SelectRenderable,
  SelectRenderableEvents,
  InputRenderableEvents,
  type KeyEvent,
  t,
  bold,
  fg,
} from "@opentui/core";
import { MeiliscanAPI, type Report, type Finding } from "./api";

// Application state
interface AppState {
  view: "welcome" | "connecting" | "dashboard" | "findings" | "finding_detail";
  api: MeiliscanAPI;
  report?: Report;
  serverUrl: string;
  apiKey: string;
  error?: string;
  selectedFindingIndex: number;
  findingFilter: {
    severity?: string;
  };
}

// Severity colors
const SEVERITY_COLORS: Record<string, string> = {
  critical: "#FF5555",
  warning: "#FFAA00",
  suggestion: "#55AAFF",
  info: "#888888",
};

const SEVERITY_SYMBOLS: Record<string, string> = {
  critical: "●",
  warning: "▲",
  suggestion: "◆",
  info: "○",
};

class MeiliscanTUI {
  private renderer!: Awaited<ReturnType<typeof createCliRenderer>>;
  private state: AppState;
  private renderableIds: string[] = [];

  constructor(apiBaseUrl: string = "http://localhost:8080") {
    this.state = {
      view: "welcome",
      api: new MeiliscanAPI(apiBaseUrl),
      serverUrl: "http://localhost:7700",
      apiKey: "",
      selectedFindingIndex: 0,
      findingFilter: {},
    };
  }

  async init() {
    this.renderer = await createCliRenderer({
      targetFps: 30,
    });

    this.setupKeyHandlers();
    this.render();
    this.renderer.start();
  }

  private setupKeyHandlers() {
    this.renderer.keyInput.on("keypress", (key: KeyEvent) => {
      // Global: Quit
      if (key.ctrl && key.name === "c") {
        this.cleanup();
        process.exit(0);
      }

      // Global: Back/Escape
      if (key.name === "escape") {
        this.goBack();
      }

      // View-specific handlers
      switch (this.state.view) {
        case "dashboard":
          this.handleDashboardKeys(key);
          break;
        case "findings":
          this.handleFindingsKeys(key);
          break;
        case "finding_detail":
          this.handleFindingDetailKeys(key);
          break;
      }
    });
  }

  private handleDashboardKeys(key: KeyEvent) {
    if (key.name === "f" || key.name === "2") {
      this.state.view = "findings";
      this.state.selectedFindingIndex = 0;
      this.render();
    } else if (key.name === "d" || key.name === "return") {
      // Disconnect/reconnect
      this.state.report = undefined;
      this.state.view = "welcome";
      this.render();
    } else if (key.name === "r") {
      // Refresh - re-analyze
      this.connect();
    }
  }

  private handleFindingsKeys(key: KeyEvent) {
    const findings = this.getFilteredFindings();

    if (key.name === "up" || key.name === "k") {
      this.state.selectedFindingIndex = Math.max(
        0,
        this.state.selectedFindingIndex - 1
      );
      this.render();
    } else if (key.name === "down" || key.name === "j") {
      this.state.selectedFindingIndex = Math.min(
        findings.length - 1,
        this.state.selectedFindingIndex + 1
      );
      this.render();
    } else if (key.name === "return") {
      if (findings.length > 0) {
        this.state.view = "finding_detail";
        this.render();
      }
    } else if (key.name === "1") {
      this.state.findingFilter.severity =
        this.state.findingFilter.severity === "critical"
          ? undefined
          : "critical";
      this.state.selectedFindingIndex = 0;
      this.render();
    } else if (key.name === "2") {
      this.state.findingFilter.severity =
        this.state.findingFilter.severity === "warning"
          ? undefined
          : "warning";
      this.state.selectedFindingIndex = 0;
      this.render();
    } else if (key.name === "3") {
      this.state.findingFilter.severity =
        this.state.findingFilter.severity === "suggestion"
          ? undefined
          : "suggestion";
      this.state.selectedFindingIndex = 0;
      this.render();
    } else if (key.name === "4") {
      this.state.findingFilter.severity =
        this.state.findingFilter.severity === "info" ? undefined : "info";
      this.state.selectedFindingIndex = 0;
      this.render();
    } else if (key.name === "0" || key.name === "a") {
      this.state.findingFilter.severity = undefined;
      this.state.selectedFindingIndex = 0;
      this.render();
    } else if (key.name === "b") {
      this.state.view = "dashboard";
      this.render();
    }
  }

  private handleFindingDetailKeys(key: KeyEvent) {
    if (key.name === "escape" || key.name === "q" || key.name === "b") {
      this.state.view = "findings";
      this.render();
    }
  }

  private goBack() {
    switch (this.state.view) {
      case "finding_detail":
        this.state.view = "findings";
        break;
      case "findings":
        this.state.view = "dashboard";
        break;
      case "dashboard":
        this.state.report = undefined;
        this.state.view = "welcome";
        break;
    }
    this.render();
  }

  private getFilteredFindings(): Finding[] {
    if (!this.state.report) return [];
    let findings = this.state.report.findings;
    if (this.state.findingFilter.severity) {
      findings = findings.filter(
        (f) => f.severity === this.state.findingFilter.severity
      );
    }
    return findings;
  }

  private cleanup() {
    // Remove all renderables by ID
    for (const id of this.renderableIds) {
      try {
        this.renderer.root.remove(id);
      } catch {}
    }
    this.renderableIds = [];
  }

  private addRenderable(renderable: { id: string }) {
    this.renderableIds.push(renderable.id);
    this.renderer.root.add(renderable);
  }

  private render() {
    // Clear existing renderables
    this.cleanup();

    switch (this.state.view) {
      case "welcome":
        this.renderWelcome();
        break;
      case "connecting":
        this.renderConnecting();
        break;
      case "dashboard":
        this.renderDashboard();
        break;
      case "findings":
        this.renderFindings();
        break;
      case "finding_detail":
        this.renderFindingDetail();
        break;
    }
  }

  private renderWelcome() {
    // Title
    const title = new TextRenderable(this.renderer, {
      id: "title",
      content: t`${bold(fg("#00AAFF")("MEILISCAN"))} - Meilisearch Configuration Analyzer`,
      position: "absolute",
      left: 2,
      top: 1,
    });
    this.addRenderable(title);

    // Version info
    const version = new TextRenderable(this.renderer, {
      id: "version",
      content: "TUI v1.0.0",
      fg: "#666666",
      position: "absolute",
      right: 2,
      top: 1,
    });
    this.addRenderable(version);

    // Connection box
    const connectBox = new BoxRenderable(this.renderer, {
      id: "connect-box",
      title: "Connect to Meilisearch",
      titleAlignment: "center",
      borderStyle: "rounded",
      borderColor: "#444444",
      width: 60,
      height: 10,
      position: "absolute",
      left: 2,
      top: 4,
    });
    this.addRenderable(connectBox);

    // URL Label
    const urlLabel = new TextRenderable(this.renderer, {
      id: "url-label",
      content: "Server URL:",
      fg: "#AAAAAA",
      position: "absolute",
      left: 4,
      top: 6,
    });
    this.addRenderable(urlLabel);

    // URL Input
    const urlInput = new InputRenderable(this.renderer, {
      id: "url-input",
      width: 40,
      placeholder: "http://localhost:7700",
      value: this.state.serverUrl,
      position: "absolute",
      left: 17,
      top: 6,
    });
    urlInput.on(InputRenderableEvents.INPUT, (value: string) => {
      this.state.serverUrl = value;
    });
    this.addRenderable(urlInput);
    urlInput.focus();

    // API Key Label
    const keyLabel = new TextRenderable(this.renderer, {
      id: "key-label",
      content: "API Key:",
      fg: "#AAAAAA",
      position: "absolute",
      left: 4,
      top: 8,
    });
    this.addRenderable(keyLabel);

    // API Key Input
    const keyInput = new InputRenderable(this.renderer, {
      id: "key-input",
      width: 40,
      placeholder: "(optional)",
      value: this.state.apiKey,
      position: "absolute",
      left: 17,
      top: 8,
    });
    keyInput.on(InputRenderableEvents.INPUT, (value: string) => {
      this.state.apiKey = value;
    });
    this.addRenderable(keyInput);

    // Connect button hint
    const connectHint = new TextRenderable(this.renderer, {
      id: "connect-hint",
      content: t`Press ${bold(fg("#00FF00")("Enter"))} to connect   ${fg("#666666")("Tab to switch fields")}`,
      position: "absolute",
      left: 4,
      top: 11,
    });
    this.addRenderable(connectHint);

    // Error message if any
    if (this.state.error) {
      const errorText = new TextRenderable(this.renderer, {
        id: "error",
        content: t`${fg("#FF5555")("Error:")} ${this.state.error}`,
        position: "absolute",
        left: 4,
        top: 13,
      });
      this.addRenderable(errorText);
    }

    // Footer
    const footer = new TextRenderable(this.renderer, {
      id: "footer",
      content: t`${fg("#666666")("Ctrl+C to quit")}`,
      position: "absolute",
      left: 2,
      bottom: 1,
    });
    this.addRenderable(footer);

    // Handle Enter to connect
    const keyHandler = (key: KeyEvent) => {
      if (key.name === "return") {
        this.renderer.keyInput.off("keypress", keyHandler);
        this.connect();
      } else if (key.name === "tab") {
        // Toggle focus between inputs
        if (urlInput.focused) {
          urlInput.blur();
          keyInput.focus();
        } else {
          keyInput.blur();
          urlInput.focus();
        }
      }
    };
    this.renderer.keyInput.on("keypress", keyHandler);
  }

  private renderConnecting() {
    const text = new TextRenderable(this.renderer, {
      id: "connecting",
      content: t`${fg("#FFAA00")("Connecting to")} ${this.state.serverUrl}...`,
      position: "absolute",
      left: 2,
      top: 2,
    });
    this.addRenderable(text);
  }

  private async connect() {
    this.state.view = "connecting";
    this.state.error = undefined;
    this.render();

    try {
      const report = await this.state.api.analyze({
        url: this.state.serverUrl,
        api_key: this.state.apiKey || undefined,
      });
      this.state.report = report;
      this.state.view = "dashboard";
    } catch (err) {
      this.state.error = err instanceof Error ? err.message : String(err);
      this.state.view = "welcome";
    }
    this.render();
  }

  private renderDashboard() {
    const report = this.state.report!;
    const summary = report.summary;

    // Title bar
    const title = new TextRenderable(this.renderer, {
      id: "title",
      content: t`${bold(fg("#00AAFF")("MEILISCAN"))} ${fg("#666666")("│")} Dashboard`,
      position: "absolute",
      left: 2,
      top: 1,
    });
    this.addRenderable(title);

    // Connection info
    const connInfo = new TextRenderable(this.renderer, {
      id: "conn-info",
      content: t`${fg("#00FF00")("●")} Connected to ${this.state.serverUrl}`,
      position: "absolute",
      right: 2,
      top: 1,
    });
    this.addRenderable(connInfo);

    // Health Score Box
    const healthColor =
      summary.health_score >= 80
        ? "#00FF00"
        : summary.health_score >= 50
          ? "#FFAA00"
          : "#FF5555";

    const healthBox = new BoxRenderable(this.renderer, {
      id: "health-box",
      title: "Health Score",
      titleAlignment: "center",
      borderStyle: "rounded",
      borderColor: healthColor,
      width: 20,
      height: 6,
      position: "absolute",
      left: 2,
      top: 3,
    });
    this.addRenderable(healthBox);

    const healthScore = new TextRenderable(this.renderer, {
      id: "health-score",
      content: t`${bold(fg(healthColor)(String(summary.health_score)))}${fg("#888888")("/100")}`,
      position: "absolute",
      left: 8,
      top: 5,
    });
    this.addRenderable(healthScore);

    const healthStatus = new TextRenderable(this.renderer, {
      id: "health-status",
      content: summary.health_status.toUpperCase(),
      fg: healthColor,
      position: "absolute",
      left: 7,
      top: 7,
    });
    this.addRenderable(healthStatus);

    // Instance Info Box
    const instanceBox = new BoxRenderable(this.renderer, {
      id: "instance-box",
      title: "Instance",
      titleAlignment: "center",
      borderStyle: "rounded",
      borderColor: "#444444",
      width: 35,
      height: 6,
      position: "absolute",
      left: 24,
      top: 3,
    });
    this.addRenderable(instanceBox);

    const instanceVersion = new TextRenderable(this.renderer, {
      id: "instance-version",
      content: t`${fg("#888888")("Version:")} ${report.instance.version || "unknown"}`,
      position: "absolute",
      left: 26,
      top: 5,
    });
    this.addRenderable(instanceVersion);

    const instanceIndexes = new TextRenderable(this.renderer, {
      id: "instance-indexes",
      content: t`${fg("#888888")("Indexes:")} ${report.instance.index_count || 0}`,
      position: "absolute",
      left: 26,
      top: 6,
    });
    this.addRenderable(instanceIndexes);

    const instanceDocs = new TextRenderable(this.renderer, {
      id: "instance-docs",
      content: t`${fg("#888888")("Documents:")} ${report.instance.total_documents?.toLocaleString() || 0}`,
      position: "absolute",
      left: 26,
      top: 7,
    });
    this.addRenderable(instanceDocs);

    // Findings Summary Box
    const findingsBox = new BoxRenderable(this.renderer, {
      id: "findings-box",
      title: "Findings",
      titleAlignment: "center",
      borderStyle: "rounded",
      borderColor: "#444444",
      width: 45,
      height: 6,
      position: "absolute",
      left: 2,
      top: 10,
    });
    this.addRenderable(findingsBox);

    const criticalCount = new TextRenderable(this.renderer, {
      id: "critical-count",
      content: t`${fg(SEVERITY_COLORS.critical)(SEVERITY_SYMBOLS.critical)} ${summary.critical_count} Critical`,
      position: "absolute",
      left: 4,
      top: 12,
    });
    this.addRenderable(criticalCount);

    const warningCount = new TextRenderable(this.renderer, {
      id: "warning-count",
      content: t`${fg(SEVERITY_COLORS.warning)(SEVERITY_SYMBOLS.warning)} ${summary.warning_count} Warning`,
      position: "absolute",
      left: 22,
      top: 12,
    });
    this.addRenderable(warningCount);

    const suggestionCount = new TextRenderable(this.renderer, {
      id: "suggestion-count",
      content: t`${fg(SEVERITY_COLORS.suggestion)(SEVERITY_SYMBOLS.suggestion)} ${summary.suggestion_count} Suggestion`,
      position: "absolute",
      left: 4,
      top: 14,
    });
    this.addRenderable(suggestionCount);

    const infoCount = new TextRenderable(this.renderer, {
      id: "info-count",
      content: t`${fg(SEVERITY_COLORS.info)(SEVERITY_SYMBOLS.info)} ${summary.info_count} Info`,
      position: "absolute",
      left: 22,
      top: 14,
    });
    this.addRenderable(infoCount);

    // Top Findings
    const topFindingsTitle = new TextRenderable(this.renderer, {
      id: "top-findings-title",
      content: t`${bold("Top Findings")}`,
      position: "absolute",
      left: 2,
      top: 17,
    });
    this.addRenderable(topFindingsTitle);

    const topFindings = report.findings.slice(0, 5);
    topFindings.forEach((finding, i) => {
      const findingText = new TextRenderable(this.renderer, {
        id: `finding-${i}`,
        content: t`${fg(SEVERITY_COLORS[finding.severity])(SEVERITY_SYMBOLS[finding.severity])} ${finding.title}`,
        position: "absolute",
        left: 4,
        top: 19 + i,
      });
      this.addRenderable(findingText);
    });

    // Navigation hints
    const navHints = new TextRenderable(this.renderer, {
      id: "nav-hints",
      content: t`${fg("#666666")("[")}${fg("#FFFFFF")("F")}${fg("#666666")("]indings  [")}${fg("#FFFFFF")("R")}${fg("#666666")("]efresh  [")}${fg("#FFFFFF")("D")}${fg("#666666")("]isconnect  [")}${fg("#FFFFFF")("Ctrl+C")}${fg("#666666")("] Quit")}`,
      position: "absolute",
      left: 2,
      bottom: 1,
    });
    this.addRenderable(navHints);
  }

  private renderFindings() {
    const findings = this.getFilteredFindings();
    const summary = this.state.report!.summary;

    // Title bar
    const title = new TextRenderable(this.renderer, {
      id: "title",
      content: t`${bold(fg("#00AAFF")("MEILISCAN"))} ${fg("#666666")("│")} Findings`,
      position: "absolute",
      left: 2,
      top: 1,
    });
    this.addRenderable(title);

    // Filter bar - each filter as separate element
    const activeFilter = this.state.findingFilter.severity;

    const filter1 = new TextRenderable(this.renderer, {
      id: "filter-1",
      content: t`${fg(activeFilter === "critical" ? "#FFFFFF" : "#666666")("[1]")} ${fg(SEVERITY_COLORS.critical)(`${summary.critical_count} Critical`)}`,
      position: "absolute",
      left: 2,
      top: 3,
    });
    this.addRenderable(filter1);

    const filter2 = new TextRenderable(this.renderer, {
      id: "filter-2",
      content: t`${fg(activeFilter === "warning" ? "#FFFFFF" : "#666666")("[2]")} ${fg(SEVERITY_COLORS.warning)(`${summary.warning_count} Warning`)}`,
      position: "absolute",
      left: 18,
      top: 3,
    });
    this.addRenderable(filter2);

    const filter3 = new TextRenderable(this.renderer, {
      id: "filter-3",
      content: t`${fg(activeFilter === "suggestion" ? "#FFFFFF" : "#666666")("[3]")} ${fg(SEVERITY_COLORS.suggestion)(`${summary.suggestion_count} Suggestion`)}`,
      position: "absolute",
      left: 34,
      top: 3,
    });
    this.addRenderable(filter3);

    const filter4 = new TextRenderable(this.renderer, {
      id: "filter-4",
      content: t`${fg(activeFilter === "info" ? "#FFFFFF" : "#666666")("[4]")} ${fg(SEVERITY_COLORS.info)(`${summary.info_count} Info`)}`,
      position: "absolute",
      left: 54,
      top: 3,
    });
    this.addRenderable(filter4);

    const filterAll = new TextRenderable(this.renderer, {
      id: "filter-all",
      content: t`${fg(!activeFilter ? "#FFFFFF" : "#666666")("[A]ll")}`,
      position: "absolute",
      left: 68,
      top: 3,
    });
    this.addRenderable(filterAll);

    // Findings count
    const countText = new TextRenderable(this.renderer, {
      id: "count",
      content: t`${fg("#888888")(`Showing ${findings.length} of ${this.state.report!.findings.length} findings`)}`,
      position: "absolute",
      right: 2,
      top: 3,
    });
    this.addRenderable(countText);

    // Findings list
    const maxVisible = 12;
    const startIdx = Math.max(
      0,
      this.state.selectedFindingIndex - Math.floor(maxVisible / 2)
    );
    const visibleFindings = findings.slice(startIdx, startIdx + maxVisible);

    visibleFindings.forEach((finding, i) => {
      const actualIdx = startIdx + i;
      const isSelected = actualIdx === this.state.selectedFindingIndex;
      const prefix = isSelected ? "▶ " : "  ";

      const findingRow = new TextRenderable(this.renderer, {
        id: `finding-row-${i}`,
        content: isSelected
          ? t`${fg("#FFFFFF")(prefix)}${fg(SEVERITY_COLORS[finding.severity])(SEVERITY_SYMBOLS[finding.severity])} ${fg("#FFFFFF")(finding.id.padEnd(10))} ${fg("#FFFFFF")(finding.title.slice(0, 50))}`
          : t`${prefix}${fg(SEVERITY_COLORS[finding.severity])(SEVERITY_SYMBOLS[finding.severity])} ${fg("#AAAAAA")(finding.id.padEnd(10))} ${finding.title.slice(0, 50)}`,
        position: "absolute",
        left: 2,
        top: 5 + i,
      });
      this.addRenderable(findingRow);
    });

    // Preview pane (if finding selected)
    if (findings.length > 0) {
      const selectedFinding = findings[this.state.selectedFindingIndex];

      const previewBox = new BoxRenderable(this.renderer, {
        id: "preview-box",
        title: "Preview",
        borderStyle: "rounded",
        borderColor: SEVERITY_COLORS[selectedFinding.severity],
        position: "absolute",
        left: 2,
        top: 18,
        width: 75,
        height: 8,
      });
      this.addRenderable(previewBox);

      const previewTitle = new TextRenderable(this.renderer, {
        id: "preview-title",
        content: t`${bold(selectedFinding.title)}`,
        position: "absolute",
        left: 4,
        top: 20,
      });
      this.addRenderable(previewTitle);

      const previewDesc = new TextRenderable(this.renderer, {
        id: "preview-desc",
        content: t`${fg("#888888")(selectedFinding.description.slice(0, 150))}${selectedFinding.description.length > 150 ? "..." : ""}`,
        position: "absolute",
        left: 4,
        top: 22,
      });
      this.addRenderable(previewDesc);

      if (selectedFinding.index_uid) {
        const previewIndex = new TextRenderable(this.renderer, {
          id: "preview-index",
          content: t`${fg("#666666")("Index:")} ${selectedFinding.index_uid}`,
          position: "absolute",
          left: 4,
          top: 24,
        });
        this.addRenderable(previewIndex);
      }
    }

    // Navigation hints
    const navHints = new TextRenderable(this.renderer, {
      id: "nav-hints",
      content: t`${fg("#666666")("[")}${fg("#FFFFFF")("↑↓")}${fg("#666666")("] Navigate  [")}${fg("#FFFFFF")("Enter")}${fg("#666666")("] Details  [")}${fg("#FFFFFF")("B")}${fg("#666666")("]ack  [")}${fg("#FFFFFF")("Ctrl+C")}${fg("#666666")("] Quit")}`,
      position: "absolute",
      left: 2,
      bottom: 1,
    });
    this.addRenderable(navHints);
  }

  private renderFindingDetail() {
    const findings = this.getFilteredFindings();
    const finding = findings[this.state.selectedFindingIndex];

    // Title bar
    const title = new TextRenderable(this.renderer, {
      id: "title",
      content: t`${bold(fg("#00AAFF")("MEILISCAN"))} ${fg("#666666")("│")} Finding Detail`,
      position: "absolute",
      left: 2,
      top: 1,
    });
    this.addRenderable(title);

    // Finding header
    const header = new TextRenderable(this.renderer, {
      id: "header",
      content: t`${fg(SEVERITY_COLORS[finding.severity])(SEVERITY_SYMBOLS[finding.severity])} ${bold(finding.title)}`,
      position: "absolute",
      left: 2,
      top: 3,
    });
    this.addRenderable(header);

    // ID
    const metaId = new TextRenderable(this.renderer, {
      id: "meta-id",
      content: t`${fg("#666666")("ID:")} ${finding.id}`,
      position: "absolute",
      left: 2,
      top: 5,
    });
    this.addRenderable(metaId);

    // Severity
    const metaSeverity = new TextRenderable(this.renderer, {
      id: "meta-severity",
      content: t`${fg("#666666")("Severity:")} ${fg(SEVERITY_COLORS[finding.severity])(finding.severity.toUpperCase())}`,
      position: "absolute",
      left: 20,
      top: 5,
    });
    this.addRenderable(metaSeverity);

    // Category
    const metaCategory = new TextRenderable(this.renderer, {
      id: "meta-category",
      content: t`${fg("#666666")("Category:")} ${finding.category}`,
      position: "absolute",
      left: 45,
      top: 5,
    });
    this.addRenderable(metaCategory);

    // Index if applicable
    if (finding.index_uid) {
      const indexInfo = new TextRenderable(this.renderer, {
        id: "index",
        content: t`${fg("#666666")("Index:")} ${finding.index_uid}`,
        position: "absolute",
        left: 2,
        top: 6,
      });
      this.addRenderable(indexInfo);
    }

    // Description
    const descTitle = new TextRenderable(this.renderer, {
      id: "desc-title",
      content: t`${bold("Description")}`,
      position: "absolute",
      left: 2,
      top: 8,
    });
    this.addRenderable(descTitle);

    const descBox = new BoxRenderable(this.renderer, {
      id: "desc-box",
      borderStyle: "rounded",
      borderColor: "#444444",
      position: "absolute",
      left: 2,
      top: 9,
      width: 75,
      height: 5,
    });
    this.addRenderable(descBox);

    const desc = new TextRenderable(this.renderer, {
      id: "desc",
      content: finding.description,
      fg: "#CCCCCC",
      position: "absolute",
      left: 4,
      top: 10,
    });
    this.addRenderable(desc);

    let currentTop = 15;

    // Recommendation
    if (finding.recommendation) {
      const recTitle = new TextRenderable(this.renderer, {
        id: "rec-title",
        content: t`${bold("Recommendation")}`,
        position: "absolute",
        left: 2,
        top: currentTop,
      });
      this.addRenderable(recTitle);

      const recBox = new BoxRenderable(this.renderer, {
        id: "rec-box",
        borderStyle: "rounded",
        borderColor: "#00AA00",
        position: "absolute",
        left: 2,
        top: currentTop + 1,
        width: 75,
        height: 4,
      });
      this.addRenderable(recBox);

      const rec = new TextRenderable(this.renderer, {
        id: "rec",
        content: finding.recommendation,
        fg: "#00FF00",
        position: "absolute",
        left: 4,
        top: currentTop + 2,
      });
      this.addRenderable(rec);

      currentTop += 6;
    }

    // Fix command
    if (finding.fix_command) {
      const fixTitle = new TextRenderable(this.renderer, {
        id: "fix-title",
        content: t`${bold("Fix Command")}`,
        position: "absolute",
        left: 2,
        top: currentTop,
      });
      this.addRenderable(fixTitle);

      const fixBox = new BoxRenderable(this.renderer, {
        id: "fix-box",
        borderStyle: "rounded",
        borderColor: "#FFAA00",
        position: "absolute",
        left: 2,
        top: currentTop + 1,
        width: 75,
        height: 4,
      });
      this.addRenderable(fixBox);

      const fix = new TextRenderable(this.renderer, {
        id: "fix",
        content: finding.fix_command,
        fg: "#FFAA00",
        position: "absolute",
        left: 4,
        top: currentTop + 2,
      });
      this.addRenderable(fix);
    }

    // Navigation hints
    const navHints = new TextRenderable(this.renderer, {
      id: "nav-hints",
      content: t`${fg("#666666")("[")}${fg("#FFFFFF")("B")}${fg("#666666")("]ack to list  [")}${fg("#FFFFFF")("Esc")}${fg("#666666")("] Back  [")}${fg("#FFFFFF")("Ctrl+C")}${fg("#666666")("] Quit")}`,
      position: "absolute",
      left: 2,
      bottom: 1,
    });
    this.addRenderable(navHints);
  }
}

// Main entry point
async function main() {
  const apiUrl = process.env.MEILISCAN_API_URL || "http://localhost:8080";

  console.log("Starting Meiliscan TUI...");
  console.log(`API URL: ${apiUrl}`);

  const tui = new MeiliscanTUI(apiUrl);
  await tui.init();
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
