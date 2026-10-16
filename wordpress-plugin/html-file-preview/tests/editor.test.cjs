'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
let filter;
const createElement = (type, props, ...children) => ({type, props, children});
const wp = {
    element: { createElement, Fragment: 'fragment' },
    i18n: { __: x => x },
    compose: { createHigherOrderComponent: x => x },
    data: { useSelect: callback => callback(name => ({getMedia: id => id === 12 ? {
        mime_type: 'text/html', source_url: 'https://andrew.local/uploads/real.html'
    } : null})) },
    hooks: { addFilter: (hook, name, callback) => {assert.equal(hook,'editor.BlockEdit'); filter=callback;} }
};
const window = { URL, location: new URL('https://andrew.local/wp-admin/post.php') };
vm.runInNewContext(fs.readFileSync(require('node:path').join(__dirname,'../assets/editor.js'), 'utf8'), {wp,window});
assert.equal(typeof filter, 'function');
const Enhanced = filter('BlockEdit');
function test(name, props, expectPreview) {
    const result = Enhanced(props);
    const withPreview = result.type === 'fragment';
    assert.equal(withPreview, expectPreview, name);
    if (withPreview) {
        assert.equal(result.children[0].type, 'BlockEdit');
        const iframe = result.children[1].children[1];
        assert.equal(iframe.type, 'iframe');
        assert.equal(iframe.props.sandbox, 'allow-scripts');
    }
    console.log('PASS:', name);
}
test('File block with .html', {name:'core/file',attributes:{href:'/uploads/file.html'}}, true);
test('File block with .htm', {name:'core/file',attributes:{href:'/uploads/file.htm?x=1'}}, true);
test('Attachment ID lookup', {name:'core/file',attributes:{id:12,href:'/attachment-page/'}}, true);
test('PDF unaffected', {name:'core/file',attributes:{href:'/uploads/file.pdf'}}, false);
test('Other blocks untouched', {name:'core/paragraph',attributes:{href:'/uploads/file.html'}}, false);
test('External HTML prevented', {name:'core/file',attributes:{href:'https://other.invalid/file.html'}}, false);
test('Protocol relative prevented', {name:'core/file',attributes:{href:'//andrew.local/file.html'}}, false);
console.log('All editor JS tests passed.');
