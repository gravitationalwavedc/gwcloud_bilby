export default {
  presets: [
    '@babel/preset-env',
    ['@babel/preset-react', { runtime: 'automatic' }],
    [
      "babel-preset-vite",
      {
        "env": true,
        "glob": false
      }
    ]
  ],
  plugins: [
    'relay'
  ]
};
