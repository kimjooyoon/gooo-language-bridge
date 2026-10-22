(function () {
    var text = "🙂";
    return JSON.stringify([
        {id: "utf16-length", input: {text: text}, result: text.length},
        {id: "code-point-count", input: {text: text}, result: Array.from(text).length},
        {id: "negative-floor", input: {dividend: -7, divisor: 3}, result: Math.floor(-7 / 3)}
    ]);
})()
