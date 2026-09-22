"use strict";

function unsupportedImageInput() {
  throw new Error("clonamic-ppt does not accept image inputs");
}

module.exports = unsupportedImageInput;
module.exports.default = unsupportedImageInput;
module.exports.imageSize = unsupportedImageInput;
