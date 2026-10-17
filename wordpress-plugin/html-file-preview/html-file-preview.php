<?php
/**
 * Plugin Name: HTML File Preview
 * Description: Adds an inline HTML preview to WordPress's built-in File block without replacing its download link.
 * Version: 0.1.0-beta.1
 * Requires at least: 6.4
 * Requires PHP: 7.4
 * License: MIT
 * License URI: https://opensource.org/license/mit
 * Text Domain: html-file-preview
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

/**
 * Return an allowed, directly previewable same-origin HTML file URL.
 * Do not enable unsafe HTML uploads or embed arbitrary third-party sites.
 *
 * @param array $attributes Core File block attributes.
 * @return string Empty string when the block does not reference a local HTML file.
 */
function hfp_preview_url( $attributes ) {
    $url = '';

    // An attachment ID identifies the actual file even when the File block's
    // link was set to its attachment page instead of the media URL.
    $id = isset( $attributes['id'] ) ? absint( $attributes['id'] ) : 0;
    if ( $id ) {
        $attachment_url = wp_get_attachment_url( $id );
        $mime           = get_post_mime_type( $id );
        if ( is_string( $attachment_url ) && 'text/html' === $mime ) {
            $url = $attachment_url;
        }
    }

    if ( ! $url && isset( $attributes['href'] ) && is_string( $attributes['href'] ) ) {
        $url = $attributes['href'];
    }

    if ( ! $url ) {
        return '';
    }

    $url   = html_entity_decode( $url, ENT_QUOTES | ENT_HTML5, 'UTF-8' );
    $parts = wp_parse_url( $url );
    $site  = wp_parse_url( home_url( '/' ) );
    if ( ! is_array( $parts ) || ! is_array( $site ) || empty( $parts['path'] ) ) {
        return '';
    }

    if ( ! preg_match( '/\.html?$/i', $parts['path'] ) ) {
        return '';
    }

    // Reject protocol-relative, external, mixed-scheme and non-HTTP URLs.
    if ( 0 === strpos( $url, '//' ) ) {
        return '';
    }
    if ( isset( $parts['host'] ) ) {
        if ( ! isset( $site['host'], $site['scheme'], $parts['scheme'] ) ) {
            return '';
        }
        if ( strtolower( $parts['host'] ) !== strtolower( $site['host'] ) ||
             strtolower( $parts['scheme'] ) !== strtolower( $site['scheme'] ) ||
             ( isset( $parts['port'] ) ? (int) $parts['port'] : null ) !==
             ( isset( $site['port'] ) ? (int) $site['port'] : null ) ) {
            return '';
        }
    } elseif ( isset( $parts['scheme'] ) ) {
        return '';
    }

    return esc_url_raw( $url, array( 'http', 'https' ) );
}

/** Add one sandboxed preview to the native File block's generated markup. */
function hfp_render_file_block( $content, $block ) {
    if ( ! is_string( $content ) || ! is_array( $block ) || empty( $block['attrs'] ) ||
         ! is_array( $block['attrs'] ) || false !== strpos( $content, 'data-hfp-preview' ) ) {
        return $content;
    }

    $url = hfp_preview_url( $block['attrs'] );
    if ( '' === $url ) {
        return $content;
    }

    $title = __( 'HTML file preview', 'html-file-preview' );
    $preview = '<div class="hfp-preview" data-hfp-preview="1">' .
        '<div class="hfp-preview__label">' . esc_html( __( 'HTML Preview', 'html-file-preview' ) ) . '</div>' .
        '<iframe class="hfp-preview__frame" src="' . esc_url( $url ) . '"' .
        ' title="' . esc_attr( $title ) . '" sandbox="allow-scripts"' .
        ' loading="lazy" referrerpolicy="no-referrer"></iframe></div>';

    // Keep WordPress's normal file link and download button completely intact.
    if ( preg_match( '/<\/div>\s*$/i', $content ) ) {
        return preg_replace( '/<\/div>(\s*)$/i', $preview . '</div>$1', $content, 1 );
    }

    return $content . $preview;
}
add_filter( 'render_block_core/file', 'hfp_render_file_block', 10, 2 );

/** Load only the editor enhancement and a small shared stylesheet. */
function hfp_enqueue_editor() {
    wp_enqueue_script(
        'hfp-editor',
        plugins_url( 'assets/editor.js', __FILE__ ),
        array( 'wp-block-editor', 'wp-compose', 'wp-data', 'wp-element', 'wp-hooks', 'wp-i18n' ),
        '0.1.0-beta.1',
        true
    );
    hfp_enqueue_styles();
}
add_action( 'enqueue_block_editor_assets', 'hfp_enqueue_editor' );

function hfp_enqueue_styles() {
    wp_enqueue_style( 'hfp-preview', plugins_url( 'assets/preview.css', __FILE__ ), array(), '0.1.0-beta.1' );
}
add_action( 'wp_enqueue_scripts', 'hfp_enqueue_styles' );
