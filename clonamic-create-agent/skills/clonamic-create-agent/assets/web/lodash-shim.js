// cytoscape-edgehandles reads memoize and throttle from window._ ; these two small versions replace lodash.
window._ = {
  memoize(fn, resolver) {
    const cache = new Map();
    const memo = function (...args) {
      const key = resolver ? resolver.apply(this, args) : args[0];
      if (!cache.has(key)) cache.set(key, fn.apply(this, args));
      return cache.get(key);
    };
    memo.cache = cache;
    return memo;
  },
  throttle(fn, wait) {
    let last = 0, timer = null, lastArgs = null;
    const run = () => { last = Date.now(); timer = null; fn(...lastArgs); };
    const throttled = (...args) => {
      lastArgs = args;
      const left = wait - (Date.now() - last);
      if (left <= 0) run();
      else if (!timer) timer = setTimeout(run, left);
    };
    throttled.cancel = () => { clearTimeout(timer); timer = null; };
    return throttled;
  },
};
