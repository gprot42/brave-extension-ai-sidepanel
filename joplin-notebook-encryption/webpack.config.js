const path = require('path');
const CopyPlugin = require('copy-webpack-plugin');

module.exports = (env) => {
  const isProduction = env && env.production;

  return {
    mode: isProduction ? 'production' : 'development',
    entry: './src/index.ts',
    target: 'node',
    module: {
      rules: [
        {
          test: /\.tsx?$/,
          use: 'ts-loader',
          exclude: /node_modules/,
        },
        {
          test: /\.css$/,
          use: ['css-loader'],
        },
      ],
    },
    resolve: {
      extensions: ['.tsx', '.ts', '.js'],
      alias: {
        // Map api imports to local api folder for TypeScript compilation
        // At runtime, Joplin provides the joplin object as a global
        'api': path.resolve(__dirname, 'api'),
      },
    },
    output: {
      filename: 'index.js',
      path: path.resolve(__dirname, 'dist'),
      // Use 'var' library type which doesn't require 'exports' global
      // Plugin registers itself via joplin.plugins.register() side effect
      library: {
        type: 'var',
        name: 'notebookEncryption',
      },
    },
    plugins: [
      new CopyPlugin({
        patterns: [
          {
            from: 'src/manifest.json',
            to: 'manifest.json',
          },
        ],
      }),
    ],
    devtool: isProduction ? false : 'source-map',
  };
};