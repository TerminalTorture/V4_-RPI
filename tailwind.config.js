/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./static/js/**/*.js",
  ],
  theme: {
    extend: {
      colors: {
        // Material Design 3 color system
        'primary': '#0D6EFD', // Updated blue
        'on-primary': '#FFFFFF',
        'primary-container': '#D0E4FF', // Updated light blue
        'on-primary-container': '#001D36', // Updated dark blue

        'secondary': '#625B71',
        'on-secondary': '#FFFFFF',
        'secondary-container': '#E8DEF8',
        'on-secondary-container': '#1E192B',
        
        'tertiary': '#7D5260',
        'on-tertiary': '#FFFFFF',
        'tertiary-container': '#FFD8E4',
        'on-tertiary-container': '#370B1E',
        
        'error': '#B3261E',
        'on-error': '#FFFFFF',
        'error-container': '#F9DEDC',
        'on-error-container': '#410E0B',
        
        'surface': '#FFFBFE',
        'on-surface': '#1C1B1F',
        'surface-variant': '#E7E0EC',
        'on-surface-variant': '#49454E',

        'outline': '#79747E',
        'background': '#FFFBFE',
        'on-background': '#1C1B1F',
      },
      borderRadius: {
        'md3-small': '8px',
        'md3-medium': '12px',
        'md3-large': '16px',
        'md3-extra-large': '28px',
      },
      boxShadow: {
        'md3-elevated-1': '0 1px 2px rgba(0, 0, 0, 0.3), 0 1px 3px 1px rgba(0, 0, 0, 0.15)',
        'md3-elevated-2': '0 1px 2px rgba(0, 0, 0, 0.3), 0 2px 6px 2px rgba(0, 0, 0, 0.15)',
        'md3-elevated-3': '0 4px 8px 3px rgba(0, 0, 0, 0.15), 0 1px 3px rgba(0, 0, 0, 0.3)',
      },
    },
  },
  plugins: [],
}