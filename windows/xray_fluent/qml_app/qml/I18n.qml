pragma Singleton
import QtQuick
import App 1.0

QtObject {
    id: i18n

    readonly property string language: App.language

    readonly property var map: App.translations

    // Catalog keys with {placeholders}, compiled once per catalog. Used to
    // translate complete backend messages (statuses, errors, toasts) that
    // already contain inserted values, mirroring i18n.translate_dynamic().
    readonly property var templates: buildTemplates(map)

    function buildTemplates(dict) {
        var result = []
        if (!dict)
            return result
        var keys = Object.keys(dict)
        for (var i = 0; i < keys.length; ++i) {
            var source = keys[i]
            if (source.indexOf("{") < 0 || !/\{\w+\}/.test(source))
                continue
            var parts = source.split(/\{(\w+)\}/)
            var literal = ""
            var names = []
            var pattern = "^"
            for (var p = 0; p < parts.length; ++p) {
                if (p % 2) {
                    names.push(parts[p])
                    pattern += "([\\s\\S]*?)"
                } else {
                    literal += parts[p]
                    pattern += parts[p].replace(/[.*+?^${}()|[\]\\\/]/g, "\\$&")
                }
            }
            // Formatting helpers such as "{secs}с" are not messages.
            var letters = literal.match(/[A-Za-z\u00C0-\u024F\u0370-\u03FF\u0400-\u04FF\u0600-\u06FF\u4E00-\u9FFF]/g)
            if (!letters || letters.length < 3)
                continue
            result.push({ source: source, names: names, re: new RegExp(pattern + "$") })
        }
        result.sort(function(a, b) { return b.source.length - a.source.length })
        return result
    }

    function dynamic(src, depth) {
        if (!/[\u0400-\u04FF]/.test(src))
            return undefined
        var dict = map
        var list = templates
        for (var i = 0; i < list.length; ++i) {
            var m = list[i].re.exec(src)
            if (!m)
                continue
            var params = {}
            for (var n = 0; n < list[i].names.length; ++n) {
                var value = m[n + 1]
                if (depth < 2 && value && /[\u0400-\u04FF]/.test(value)) {
                    var exact = dict[value]
                    if (exact !== undefined) {
                        value = exact
                    } else {
                        var nested = dynamic(value, depth + 1)
                        if (nested !== undefined)
                            value = nested
                    }
                }
                if (params[list[i].names[n]] === undefined)
                    params[list[i].names[n]] = value
            }
            return dict[list[i].source].replace(/\{(\w+)\}/g, function(full, name) {
                return (params[name] !== undefined) ? ("" + params[name]) : full
            })
        }
        return undefined
    }

    function t(msgid, params) {
        if (msgid === undefined || msgid === null)
            return ""
        var src = "" + msgid
        var dict = map
        var text
        if (dict && dict[src] !== undefined) {
            text = dict[src]
        } else if (dict && (params === undefined || params === null) && src.length > 0) {
            var translated = dynamic(src, 0)
            text = translated !== undefined ? translated : src
        } else {
            text = src
        }
        if (params !== undefined && params !== null) {
            text = text.replace(/\{(\w+)\}/g, function(full, name) {
                return (params[name] !== undefined) ? ("" + params[name]) : full
            })
        }
        return text
    }
}
