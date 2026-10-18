/* global wp, window, hfpEditorSettings */
( function () {
    'use strict';

    var el = wp.element.createElement;
    var Fragment = wp.element.Fragment;
    var __ = wp.i18n.__;
    var DEFAULT_HEIGHT = 600;
    var MIN_HEIGHT = 100;
    var MAX_HEIGHT = 2000;

    function clampHeight( value ) {
        var n = Number( value );
        if ( !Number.isFinite( n ) ) {
            return DEFAULT_HEIGHT;
        }
        return Math.max( MIN_HEIGHT, Math.min( MAX_HEIGHT, Math.round( n ) ) );
    }

    function localHtmlUrl( url ) {
        if ( typeof url !== 'string' || !url.trim() || url.slice( 0, 2 ) === '//' ) {
            return '';
        }
        try {
            var base = ( typeof hfpEditorSettings !== 'undefined' && hfpEditorSettings.siteUrl ) || window.location.origin + '/';
            var site = new window.URL( base );
            var parsed = new window.URL( url, base );
            if ( parsed.origin !== site.origin ||
                 !/^https?:$/.test( parsed.protocol ) ||
                 parsed.username || parsed.password ||
                 !/\.html?$/i.test( parsed.pathname ) ) {
                return '';
            }
            return parsed.href;
        } catch ( e ) {
            return '';
        }
    }

    var htmlAttributes = {
        hfpShowPreview: { type: 'boolean', default: false },
        hfpPreviewHeight: { type: 'number', default: DEFAULT_HEIGHT }
    };

    wp.hooks.addFilter( 'blocks.registerBlockType', 'html-file-preview/file-attributes', function ( settings, name ) {
        if ( name !== 'core/file' ) {
            return settings;
        }
        return Object.assign( {}, settings, {
            attributes: Object.assign( {}, settings.attributes, htmlAttributes )
        } );
    } );

    // Core blocks can be registered before enqueue_block_editor_assets runs.
    // Keep the already-registered core/file schema in sync in that case.
    if ( wp.blocks && typeof wp.blocks.getBlockType === 'function' ) {
        var existing = wp.blocks.getBlockType( 'core/file' );
        if ( existing && existing.attributes && Object.isExtensible( existing.attributes ) ) {
            Object.assign( existing.attributes, htmlAttributes );
        }
    }

    var withHtmlFilePreview = wp.compose.createHigherOrderComponent( function ( BlockEdit ) {
        return function ( props ) {
            // A consistent hook order is required even as blocks are switched.
            var media = wp.data.useSelect( function ( select ) {
                var id = props.name === 'core/file' && props.attributes && props.attributes.id;
                var core = select( 'core' );
                return id && core && typeof core.getMedia === 'function' ? core.getMedia( id ) : null;
            }, [ props.name, props.attributes && props.attributes.id ] );

            if ( props.name !== 'core/file' ) {
                return el( BlockEdit, props );
            }

            var attrs = props.attributes || {};
            // Prioritize the actual Media Library URL: the visible File link may
            // have been changed to an attachment page rather than the file.
            var mediaUrl = media && media.source_url && localHtmlUrl( media.source_url );
            var url = mediaUrl || localHtmlUrl( attrs.href ) || localHtmlUrl( attrs.textLinkHref );
            // The Media REST lookup is asynchronous, and the File link may be
            // configured to point to an attachment page (without .html suffix).
            // Do NOT make the Inspector toggle depend on that lookup completing.
            // A File with an unresolved attachment ID can still show controls;
            // backend validation guarantees no non-HTML iframe is rendered.
            var knownNonHtmlMedia = media && media.mime_type &&
                media.mime_type !== 'text/html' && media.mime_type !== 'application/xhtml+xml';
            var explicitNonHtmlLink = /\.(?:pdf|ics|png|jpe?g|gif|webp|svg|docx?|xlsx?|pptx?|zip|mp4|mp3)(?:[?#]|$)/i.test( attrs.href || '' );
            var candidate = !!url || attrs.hfpShowPreview === true ||
                (!!attrs.id && !knownNonHtmlMedia && !explicitNonHtmlLink);
            if ( !candidate ) {
                return el( BlockEdit, props );
            }

            var visible = attrs.hfpShowPreview === true;
            var height = clampHeight( attrs.hfpPreviewHeight === undefined ? DEFAULT_HEIGHT : attrs.hfpPreviewHeight );
            var controls = props.isSelected && el( wp.blockEditor.InspectorControls, null,
                el( wp.components.PanelBody, {
                    title: __( 'HTML preview', 'html-file-preview' ),
                    initialOpen: true
                },
                    el( wp.components.ToggleControl, {
                        label: __( 'Show inline embed', 'html-file-preview' ),
                        checked: visible,
                        onChange: function ( value ) { props.setAttributes( { hfpShowPreview: !!value } ); }
                    } ),
                    visible && !url && el( 'p', { className: 'hfp-preview__notice' },
                        __( 'Waiting for an HTML attachment URL. No preview will be displayed until a valid local HTML URL is available.', 'html-file-preview' ) ),
                    visible && el( wp.components.TextControl, {
                        label: __( 'Height in pixels', 'html-file-preview' ),
                        value: height,
                        min: MIN_HEIGHT,
                        max: MAX_HEIGHT,
                        type: 'number',
                        onChange: function ( value ) {
                            if ( value !== '' ) {
                                props.setAttributes( { hfpPreviewHeight: clampHeight( value ) } );
                            }
                        }
                    } )
                )
            );

            return el( Fragment, null,
                el( BlockEdit, props ),
                controls,
                visible && !!url && el( 'div', { className: 'hfp-preview hfp-preview--editor', 'data-hfp-preview': '1' },
                    el( 'iframe', {
                        className: 'hfp-preview__frame',
                        src: url,
                        title: __( 'HTML file preview', 'html-file-preview' ),
                        style: { height: height + 'px' },
                        sandbox: 'allow-scripts',
                        loading: 'lazy',
                        referrerPolicy: 'no-referrer'
                    } )
                )
            );
        };
    }, 'withHtmlFilePreview' );

    wp.hooks.addFilter( 'editor.BlockEdit', 'html-file-preview/core-file', withHtmlFilePreview );

    // Read-only, opt-in troubleshooting from the editor browser console:
    // window.hfpPreviewRuntime (does not log content or credentials).
    window.hfpPreviewRuntime = {
        loaded: true,
        version: typeof hfpEditorSettings !== 'undefined' ? hfpEditorSettings.version : 'unknown',
        coreFileRegistered: !!( wp.blocks && wp.blocks.getBlockType && wp.blocks.getBlockType( 'core/file' ) ),
        settingsRegistered: !!( wp.blocks && wp.blocks.getBlockType && wp.blocks.getBlockType( 'core/file' ) &&
            wp.blocks.getBlockType( 'core/file' ).attributes &&
            wp.blocks.getBlockType( 'core/file' ).attributes.hfpShowPreview )
    };
}() );
