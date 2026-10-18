'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const filters = {};
const existingFile = { attributes: { href: { type: 'string' }, displayPreview: { type: 'boolean' } } };
const createElement = (type, props, ...children) => ({ type, props: props || {}, children });
const wp = {
    element: { createElement, Fragment: 'Fragment' },
    i18n: { __: x => x },
    compose: { createHigherOrderComponent: x => x },
    blocks: { getBlockType: name => name === 'core/file' ? existingFile : null },
    blockEditor: { InspectorControls: 'InspectorControls' },
    components: { PanelBody: 'PanelBody', ToggleControl: 'ToggleControl', TextControl: 'TextControl' },
    data: { useSelect: callback => callback(name => ({ getMedia: id => id === 12 ? {
        mime_type: 'text/html', source_url: 'https://andrew.local/uploads/real.html'
    } : null })) },
    hooks: { addFilter: (hook, name, callback) => { filters[hook] = callback; } }
};
const window = { URL, location: new URL('https://andrew.local/wp-admin/post.php') };
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../assets/editor.js'), 'utf8'), {
    wp, window, hfpEditorSettings: { siteUrl: 'https://andrew.local/' }
});
function check(name, truth) { assert.ok(truth, name); console.log('PASS:', name); }
check('runtime script reports loaded status', window.hfpPreviewRuntime.loaded === true);
check('client attrs registered on already-registered core/file', existingFile.attributes.hfpShowPreview.default === false && existingFile.attributes.hfpPreviewHeight.default === 600);
const merged = filters['blocks.registerBlockType']({ attributes: { href: {} } }, 'core/file');
check('client attrs added for later core/file registrations', merged.attributes.hfpPreviewHeight.default === 600 && 'href' in merged.attributes);
check('other block schemas unchanged', filters['blocks.registerBlockType']({ attributes: {} }, 'core/paragraph').attributes.hfpPreviewHeight === undefined);
const Enhanced = filters['editor.BlockEdit']('BlockEdit');
function render(attrs, options = {}) {
    return Enhanced({
        name: options.name || 'core/file', attributes: attrs, isSelected: options.isSelected !== false,
        setAttributes: options.setAttributes || (() => {})
    });
}
function child(root, type) { return root.children.find(item => item && item.type === type); }
function locatePanel(result) {
    const inspector = child(result, 'InspectorControls');
    return inspector && child(inspector, 'PanelBody');
}
function verifyEditorWithoutIframe(name, attrs) {
    const result = render(attrs);
    check(name + ' returns a fragment', result.type === 'Fragment');
    check(name + ' does NOT create iframe by default', !child(result, 'div'));
    check(name + ' preserves native editor', !!child(result, 'BlockEdit'));
    const panel = locatePanel(result);
    check(name + ' has HTML preview settings', !!panel);
    const toggle = child(panel, 'ToggleControl');
    check(name + ' preview toggle starts off', toggle.props.checked === false);
}
verifyEditorWithoutIframe('HTML direct URL', { href: '/uploads/a.html' });
verifyEditorWithoutIframe('HTM query string', { href: '/uploads/a.htm?ver=1' });
verifyEditorWithoutIframe('HTML attachment ID', { id: 12, href: '/attachment-page/' });
verifyEditorWithoutIframe('alternative File URL', { textLinkHref: '/uploads/alternate.html' });
verifyEditorWithoutIframe('pending attachment REST lookup', { id: 44, href: '/attachment-page/' });
const toggles = [];
const result = render({ href: '/uploads/a.html' }, { setAttributes: x => toggles.push(x) });
const panel = locatePanel(result);
check('HTML inspector shown in File block', panel && panel.props.title === 'HTML preview');
const toggle = child(panel, 'ToggleControl');
check('toggle label follows PDF inline embed setting', toggle.props.label === 'Show inline embed');
toggle.props.onChange(true);
check('enabling preview writes explicit true', toggles[0].hfpShowPreview === true);
const enabled = render({ href: '/uploads/a.html', hfpShowPreview: true, hfpPreviewHeight: 875 }, {
    setAttributes: x => toggles.push(x)
});
const enabledPanel = locatePanel(enabled);
const iframeWrapper = child(enabled, 'div');
check('enabled HTML iframe rendered', !!iframeWrapper && child(iframeWrapper, 'iframe').props.style.height === '875px');
check('enabled HTML iframe sandbox preserves opacity', child(iframeWrapper, 'iframe').props.sandbox === 'allow-scripts');
const onToggle = child(enabledPanel, 'ToggleControl');
check('enabled switch is on', onToggle.props.checked === true);
onToggle.props.onChange(false);
check('explicit off is written', toggles[1].hfpShowPreview === false);
const heightControl = child(enabledPanel, 'TextControl');
check('enabled height control available', heightControl.props.label === 'Height in pixels' && heightControl.props.value === 875);
heightControl.props.onChange(850);
check('height is saved per block', toggles[2].hfpPreviewHeight === 850);
let off = render({ href: '/uploads/a.html', hfpShowPreview: false });
check('disabled HTML iframe not rendered', off.type === 'Fragment' && !child(off, 'div'));
check('height control hidden when disabled', !child(locatePanel(off), 'TextControl'));
check('native File editor still rendered', child(off, 'BlockEdit'));
const unresolved = render({ id: 44, href: '/attachment-page/', hfpShowPreview: true });
check('unresolved HTML candidate has inspector but no iframe', !!locatePanel(unresolved) && !child(unresolved,'div'));
check('PDF File native editor unchanged', render({ href: '/uploads/a.pdf', displayPreview: true }).type === 'BlockEdit');
check('other block unchanged', render({ href: '/uploads/a.html' }, { name: 'core/paragraph' }).type === 'BlockEdit');
check('external HTML rejected', render({ href: 'https://other.example/a.html' }).type === 'BlockEdit');
check('protocol-relative HTML rejected', render({ href: '//andrew.local/a.html' }).type === 'BlockEdit');
check('JS-scheme rejected', render({ href: 'javascript:alert(1).html' }).type === 'BlockEdit');
check('credentialed URL rejected', render({ href: 'https://u:p@andrew.local/a.html' }).type === 'BlockEdit');
check('unselected HTML block off without preview', !child(render({ href: '/uploads/a.html' }, { isSelected: false }), 'div'));
check('unselected HTML block no inspector', !child(render({ href: '/uploads/a.html' }, { isSelected: false }), 'InspectorControls'));
console.log('All editor JS tests passed.');
