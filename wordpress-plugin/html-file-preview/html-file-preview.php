<?php
/**
 * Plugin Name: HTML File Preview
 * Description: Gives same-site HTML and HTM attachments a PDF-style inline preview and per-block preview settings in the native File block.
 * Version: 0.2.2-beta.1
 * Requires at least: 6.4
 * Requires PHP: 7.4
 * License: MIT
 * License URI: https://opensource.org/license/mit
 * Text Domain: html-file-preview
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

define( 'HFP_VERSION', '0.2.2-beta.1' );

/**
 * Register persisted HTML-only settings on core/file (not a replacement block).
 * Safe default: false. No automatic previews in old or new File blocks.
 * The separate names are intentional: core/file uses displayPreview for PDF
 * and serializes an application/pdf object when that value is true.
 */
function hfp_register_file_attributes( $args, $block_type ) {
    if ( 'core/file' !== $block_type ) {
        return $args;
    }

    if ( ! isset( $args['attributes'] ) || ! is_array( $args['attributes'] ) ) {
        $args['attributes'] = array();
    }
    $args['attributes']['hfpShowPreview'] = array(
        'type'    => 'boolean',
        'default' => false,
    );
    $args['attributes']['hfpPreviewHeight'] = array(
        'type'    => 'number',
        'default' => 600,
    );
    return $args;
}
add_filter( 'register_block_type_args', 'hfp_register_file_attributes', 10, 2 );

/** Limit a saved preview height to a usable pixel range. */
function hfp_preview_height( $attrs ) {
    $raw = isset( $attrs['hfpPreviewHeight'] ) ? $attrs['hfpPreviewHeight'] : 600;
    if ( ! is_numeric( $raw ) ) {
        return 600;
    }
    return max( 100, min( 2000, (int) round( (float) $raw ) ) );
}

/**
 * Resolve a same-origin HTML URL for the File block. No remote fetching.
 * Prefer the direct attachment URL, even if the visible link goes to its page.
 */
function hfp_preview_url( $attributes ) {
    if ( ! is_array( $attributes ) ) {
        return '';
    }
    $url = '';
    $id  = isset( $attributes['id'] ) ? absint( $attributes['id'] ) : 0;
    if ( $id ) {
        $attachment_url = wp_get_attachment_url( $id );
        $mime           = get_post_mime_type( $id );
        if ( is_string( $attachment_url ) && 'text/html' === $mime ) {
            $url = $attachment_url;
        }
    }
    // On newer File block variations the visible link can be stored separately.
    if ( ! $url ) {
        foreach ( array( 'href', 'textLinkHref' ) as $key ) {
            if ( isset( $attributes[ $key ] ) && is_string( $attributes[ $key ] ) &&
                 preg_match( '/\.html?(?:[?#]|$)/i', $attributes[ $key ] ) ) {
                $url = $attributes[ $key ];
                break;
            }
        }
    }
    $url = trim( $url );
    if ( '' === $url || 0 === strpos( $url, '//' ) ) {
        return '';
    }
    $url   = html_entity_decode( $url, ENT_QUOTES | ENT_HTML5, 'UTF-8' );
    $parts = wp_parse_url( $url );
    $site  = wp_parse_url( home_url( '/' ) );
    if ( ! is_array( $parts ) || ! is_array( $site ) || empty( $parts['path'] ) ||
         empty( $site['scheme'] ) || empty( $site['host'] ) ||
         ! preg_match( '/\.html?$/i', $parts['path'] ) ||
         isset( $parts['user'] ) || isset( $parts['pass'] ) ) {
        return '';
    }

    $origin = strtolower( $site['scheme'] ) . '://' . $site['host'];
    if ( isset( $site['port'] ) ) {
        $origin .= ':' . $site['port'];
    }

    if ( isset( $parts['host'] ) ) {
        if ( ! isset( $parts['scheme'] ) ||
             strtolower( $parts['scheme'] ) !== strtolower( $site['scheme'] ) ||
             strtolower( $parts['host'] ) !== strtolower( $site['host'] ) ||
             ( isset( $parts['port'] ) ? (int) $parts['port'] : null ) !==
             ( isset( $site['port'] ) ? (int) $site['port'] : null ) ) {
            return '';
        }
    } elseif ( isset( $parts['scheme'] ) ) {
        return '';
    } else {
        // Browser-independent resolution: do not resolve paths relative to a post.
        if ( '/' === $url[0] ) {
            $url = $origin . $url;
        } else {
            $url = trailingslashit( home_url( '/' ) ) . $url;
        }
    }

    return esc_url_raw( $url, array( 'http', 'https' ) );
}

/**
 * Enhance front-end/rendered core/file markup without modifying the saved
 * filename link or download button. The iframe stays sandboxed with an opaque
 * origin: scripts are allowed, allow-same-origin deliberately is NOT.
 */
function hfp_render_file_block( $content, $block ) {
    if ( ! is_string( $content ) || ! is_array( $block ) ||
         ! isset( $block['attrs'] ) || ! is_array( $block['attrs'] ) ||
         false !== strpos( $content, 'data-hfp-preview=' ) ) {
        return $content;
    }

    $attrs = $block['attrs'];
    // Opt-in only. Older posts have no hfpShowPreview attribute: do NOT
    // silently add iframes merely because the plugin is activated.
    if ( ! isset( $attrs['hfpShowPreview'] ) || true !== $attrs['hfpShowPreview'] ) {
        return $content;
    }
    $url = hfp_preview_url( $attrs );
    if ( '' === $url ) {
        return $content;
    }

    $preview = '<div class="hfp-preview" data-hfp-preview="1">' .
        '<iframe class="hfp-preview__frame" src="' . esc_url( $url ) . '"' .
        ' title="' . esc_attr( __( 'HTML file preview', 'html-file-preview' ) ) . '"' .
        ' style="height:' . hfp_preview_height( $attrs ) . 'px"' .
        ' sandbox="allow-scripts" loading="lazy" referrerpolicy="no-referrer"></iframe>' .
        '</div>';

    // Insert inside the original WordPress File block wrapper; no link rewrites.
    if ( preg_match( '/<\/div>\s*$/i', $content ) ) {
        return preg_replace( '/<\/div>(\s*)$/i', $preview . '</div>$1', $content, 1 );
    }
    return $content . $preview;
}
add_filter( 'render_block_core/file', 'hfp_render_file_block', 10, 2 );

/** Editor settings + interactive native File controls. */
function hfp_enqueue_editor() {
    wp_enqueue_script(
        'hfp-editor',
        plugins_url( 'assets/editor.js', __FILE__ ),
        array( 'wp-blocks', 'wp-block-editor', 'wp-components', 'wp-compose', 'wp-data', 'wp-element', 'wp-hooks', 'wp-i18n' ),
        HFP_VERSION . '.' . filemtime( __DIR__ . '/assets/editor.js' ),
        true
    );
    wp_localize_script( 'hfp-editor', 'hfpEditorSettings', array( 'siteUrl' => home_url( '/' ), 'version' => HFP_VERSION ) );
    hfp_enqueue_styles();
}
add_action( 'enqueue_block_editor_assets', 'hfp_enqueue_editor' );

function hfp_enqueue_styles() {
    wp_enqueue_style( 'hfp-preview', plugins_url( 'assets/preview.css', __FILE__ ), array(), HFP_VERSION . '.' . filemtime( __DIR__ . '/assets/preview.css' ) );
}
add_action( 'wp_enqueue_scripts', 'hfp_enqueue_styles' );

/**
 * Read-only diagnostics, available at Tools -> HTML Preview.
 * This is deliberately a diagnostic screen, not a parallel block settings UI.
 */
function hfp_register_diagnostics_page() {
    add_management_page(
        __( 'HTML File Preview Diagnostics', 'html-file-preview' ),
        __( 'HTML Preview Diagnostics', 'html-file-preview' ),
        'edit_posts',
        'hfp-diagnostics',
        'hfp_show_diagnostics_page'
    );
}
add_action( 'admin_menu', 'hfp_register_diagnostics_page' );

function hfp_diagnose_block( $block, &$stats ) {
    $name = isset( $block['blockName'] ) ? $block['blockName'] : '';
    if ( 'core/file' === $name ) {
        ++$stats['file_blocks'];
        $url = hfp_preview_url( isset( $block['attrs'] ) ? $block['attrs'] : array() );
        if ( $url ) {
            ++$stats['html_file_blocks'];
        }
    } elseif ( 'core/html' === $name ) {
        ++$stats['custom_html_blocks'];
    } elseif ( 'core/embed' === $name ) {
        ++$stats['embed_blocks'];
    }
    if ( ! empty( $block['innerBlocks'] ) && is_array( $block['innerBlocks'] ) ) {
        foreach ( $block['innerBlocks'] as $inner ) {
            hfp_diagnose_block( $inner, $stats );
        }
    }
}

function hfp_show_diagnostics_page() {
    if ( ! current_user_can( 'edit_posts' ) ) {
        wp_die( esc_html__( 'You do not have permission to view this screen.', 'html-file-preview' ) );
    }
    $post_id = isset( $_GET['hfp_post_id'] ) ? absint( $_GET['hfp_post_id'] ) : 0;
    echo '<div class="wrap"><h1>' . esc_html__( 'HTML File Preview Diagnostics', 'html-file-preview' ) . '</h1>';
    echo '<p>Plugin version: <strong>' . esc_html( HFP_VERSION ) . '</strong></p>';
    echo '<p>Plugin file: <code>' . esc_html( __FILE__ ) . '</code></p>';
    echo '<p>Editor asset: <code>' . esc_html( plugins_url( 'assets/editor.js', __FILE__ ) ) . '</code></p>';
    echo '<p>File block registered on server: <strong>' . ( WP_Block_Type_Registry::get_instance()->is_registered( 'core/file' ) ? 'yes' : 'no' ) . '</strong></p>';
    echo '<form method="get"><input type="hidden" name="page" value="hfp-diagnostics">';
    echo '<label for="hfp_post_id">Inspect post/page ID: </label><input id="hfp_post_id" type="number" min="1" name="hfp_post_id" value="' . esc_attr( $post_id ?: '' ) . '"> ';
    submit_button( 'Inspect', 'secondary', '', false );
    echo '</form>';
    if ( $post_id ) {
        $post = get_post( $post_id );
        if ( ! $post || ! current_user_can( 'edit_post', $post_id ) ) {
            echo '<p>Post not found or not accessible.</p>';
        } else {
            $stats = array( 'file_blocks' => 0, 'html_file_blocks' => 0, 'custom_html_blocks' => 0, 'embed_blocks' => 0 );
            foreach ( parse_blocks( $post->post_content ) as $block ) {
                hfp_diagnose_block( $block, $stats );
            }
            echo '<h2>' . esc_html( $post->post_title ) . '</h2><table class="widefat striped" style="max-width:560px"><tbody>';
            foreach ( $stats as $key => $value ) {
                echo '<tr><th>' . esc_html( $key ) . '</th><td>' . esc_html( $value ) . '</td></tr>';
            }
            echo '</tbody></table>';
            if ( ! $stats['html_file_blocks'] ) {
                echo '<p><strong>No compatible HTML File block found.</strong> The plugin only adds controls when an actual core/file block references a same-site .html/.htm URL. Custom HTML and Embed blocks do not get these settings.</p>';
            }
        }
    }
    echo '</div>';
}
