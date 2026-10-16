/* global wp, window */
( function () {
    'use strict';
    var el = wp.element.createElement;
    var Fragment = wp.element.Fragment;
    var __ = wp.i18n.__;

    // Never preview an arbitrary off-site or non-HTML URL in the editor.
    function localHtmlUrl( url ) {
        if ( typeof url !== 'string' || !url || url.slice( 0, 2 ) === '//' ) {
            return '';
        }
        try {
            var parsed = new window.URL( url, window.location.href );
            if ( parsed.origin !== window.location.origin || !/\.html?$/i.test( parsed.pathname ) ) {
                return '';
            }
            return parsed.href;
        } catch ( e ) {
            return '';
        }
    }

    var withHtmlFilePreview = wp.compose.createHigherOrderComponent( function ( BlockEdit ) {
        return function ( props ) {
            // The hook is called unconditionally for a stable hook order.
            var media = wp.data.useSelect( function ( select ) {
                var id = props.name === 'core/file' && props.attributes && props.attributes.id;
                return id ? select( 'core' ).getMedia( id ) : null;
            }, [ props.name, props.attributes && props.attributes.id ] );

            if ( props.name !== 'core/file' ) {
                return el( BlockEdit, props );
            }
            var url = media && ( media.mime_type === 'text/html' || media.mime === 'text/html' ) && media.source_url ? media.source_url :
                props.attributes && props.attributes.href;
            url = localHtmlUrl( url );
            if ( !url ) {
                return el( BlockEdit, props );
            }
            return el( Fragment, null,
                el( BlockEdit, props ),
                el( 'div', { className: 'hfp-preview hfp-preview--editor', 'data-hfp-preview': '1' },
                    el( 'div', { className: 'hfp-preview__label' }, __( 'HTML Preview', 'html-file-preview' ) ),
                    el( 'iframe', {
                        className: 'hfp-preview__frame',
                        src: url,
                        title: __( 'HTML file preview', 'html-file-preview' ),
                        sandbox: 'allow-scripts',
                        loading: 'lazy',
                        referrerPolicy: 'no-referrer'
                    } )
                )
            );
        };
    }, 'withHtmlFilePreview' );

    wp.hooks.addFilter( 'editor.BlockEdit', 'html-file-preview/core-file', withHtmlFilePreview );
}() );
