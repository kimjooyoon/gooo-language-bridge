(function () {
  var rows = [];
  var samples = [
    ["lone-high", "\ud800"],
    ["lone-low", "\udfff"],
    ["separated", "\ud800e\u0301\udfff"],
    ["valid-pair", "\ud83d\ude42"],
    ["combining", "e\u0301"],
    ["replacement", "\ufffd"]
  ];
  function units(s) {
    var result = [];
    for (var i = 0; i < s.length; i++) result.push(s.charCodeAt(i));
    return result;
  }
  for (var i = 0; i < samples.length; i++) {
    for (var j = 0; j < 4; j++) {
      var form = ["NFC", "NFD", "NFKC", "NFKD"][j];
      rows.push({id:samples[i][0]+"/"+form, input:units(samples[i][1]), result:units(samples[i][1].normalize(form))});
    }
  }
  return JSON.stringify(rows);
})()
