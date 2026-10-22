(function () {
    var factories = [
        ['undefined', function () {}],
        ['null', function () { return null; }],
        ['boolean', function () { return false; }],
        ['number', function () { return 0; }],
        ['nan', function () { return NaN; }],
        ['string', function () { return 'reviver'; }],
        ['object', function () { return {}; }],
        ['array', function () { return []; }],
        ['symbol', function () { return Symbol('reviver'); }],
        ['bigint', function () { return BigInt(1); }],
        ['poison-object', function () {
            var value = {};
            Object.defineProperty(value, Symbol.toPrimitive, {get: function () { throw Error('must not coerce'); }});
            return value;
        }],
        ['revoked-object', function () {
            var pair = Proxy.revocable({}, {}); pair.revoke(); return pair.proxy;
        }],
        ['identity', function (calls) { return function (key, value) {
            'use strict';
            calls.push([key, typeof value, Object.prototype.hasOwnProperty.call(this, key)]);
            return value;
        }; }],
        ['double', function (calls) { return function (key, value) {
            calls.push(key); return typeof value === 'number' ? value * 2 : value;
        }; }],
        ['delete', function (calls) { return function (key, value) {
            calls.push(key); return key === 'value' ? undefined : value;
        }; }],
        ['throws', function (calls) { return function (key) {
            calls.push(key); throw Error('reviver failed');
        }; }],
        ['callable-proxy', function (calls) { return new Proxy(function (key, value) {
            calls.push(['target', key]); return value;
        }, {apply: function (target, holder, args) {
            calls.push(['proxy', args[0], Object.prototype.hasOwnProperty.call(holder, args[0])]);
            return Reflect.apply(target, holder, args);
        }}); }],
        ['revoked-callable', function () {
            var pair = Proxy.revocable(function (key, value) { return value; }, {});
            pair.revoke(); return pair.proxy;
        }]
    ];
    var inputs = [['scalar', '42'], ['array', '[1,{"value":2}]'], ['object', '{"value":42}']];
    var rows = [];
    for (var i = 0; i < inputs.length; i++) {
        for (var j = 0; j < factories.length; j++) {
            var calls = [], reviver = factories[j][1](calls), result;
            try {
                var value = JSON.parse(inputs[i][1], reviver);
                result = {value: value, calls: calls};
            } catch (error) {
                // Engine-specific message text is deliberately outside this observation.
                result = {error: error.name, calls: calls};
            }
            rows.push({id: inputs[i][0] + '/' + factories[j][0],
                input: {json: inputs[i][1], reviver: factories[j][0]}, result: result});
        }
    }
    return JSON.stringify(rows);
})()
