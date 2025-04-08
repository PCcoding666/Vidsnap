module.exports = {
  webpack: {
    configure: {
      module: {
        rules: [
          {
            test: /\.less$/,
            use: [
              {
                loader: 'source-map-loader',
                options: {
                  filterSourceMappingUrl: (url, resourcePath) => {
                    return false;
                  },
                },
              },
            ],
          },
        ],
      },
    },
  },
}; 