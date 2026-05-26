export const setPageTitle = (title?: string): void => {
  document.title = title ? `${title} - QuantCell` : 'QuantCell - 量化交易平台';
};
