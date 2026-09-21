.pragma library

function localPath(url) {
    const value = String(url);
    if (!value.startsWith("file://")) throw new Error("Omatask requires a local plugin directory");
    return decodeURIComponent(value.slice(7));
}

function command(settings, bundledUrl) {
    const values = settings || {};
    const executable = String(values.executable || "");
    // Run through Python so a checkout or source archive need not preserve +x.
    const args = executable ? [executable] : ["/usr/bin/python3", localPath(bundledUrl)];
    if (values.database) args.push("--db", String(values.database));
    return args;
}

function widgetSettings(barConfig) {
    const layout = (barConfig || {}).layout || {};
    for (const section of ["left", "center", "right"]) {
        for (const entry of (layout[section] || [])) {
            if (entry && entry.id === "local.omatask") return entry;
        }
    }
    return {};
}
