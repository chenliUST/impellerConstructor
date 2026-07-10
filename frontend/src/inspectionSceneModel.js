const GEOMETRIC_VIEW_IDS = new Set(["3d", "meridional", "top"]);

export function createRendererLifecycleRegistry() {
  const counts = {
    createdRendererCount: 0,
    liveRendererCount: 0,
    createdContextCount: 0,
    liveContextCount: 0,
  };
  return {
    register(renderer) {
      const context = renderer?.getContext?.() || null;
      counts.createdRendererCount += 1;
      counts.liveRendererCount += 1;
      if (context) {
        counts.createdContextCount += 1;
        counts.liveContextCount += 1;
      }
      let released = false;
      return () => {
        if (released) {
          return;
        }
        released = true;
        counts.liveRendererCount -= 1;
        if (context) {
          counts.liveContextCount -= 1;
        }
      };
    },
    snapshot() {
      return { ...counts };
    },
  };
}

export const inspectionRendererLifecycle = createRendererLifecycleRegistry();

export function inspectionViewportRects(width, height, layout) {
  const viewportWidth = finiteDimension(width);
  const viewportHeight = finiteDimension(height);
  if (layout === "quad_stacked") {
    const firstBoundary = Math.floor(viewportHeight / 4);
    const secondBoundary = Math.floor(viewportHeight / 2);
    const thirdBoundary = Math.floor((viewportHeight * 3) / 4);
    return {
      "3d": { x: 0, y: thirdBoundary, width: viewportWidth, height: viewportHeight - thirdBoundary },
      meridional: { x: 0, y: secondBoundary, width: viewportWidth, height: thirdBoundary - secondBoundary },
      "s_q": { x: 0, y: firstBoundary, width: viewportWidth, height: secondBoundary - firstBoundary },
      top: { x: 0, y: 0, width: viewportWidth, height: firstBoundary },
    };
  }
  if (layout !== "quad") {
    return {
      [layout]: { x: 0, y: 0, width: viewportWidth, height: viewportHeight },
    };
  }

  const leftWidth = Math.floor(viewportWidth / 2);
  const rightWidth = viewportWidth - leftWidth;
  const bottomHeight = Math.floor(viewportHeight / 2);
  const topHeight = viewportHeight - bottomHeight;
  return {
    "3d": { x: 0, y: bottomHeight, width: leftWidth, height: topHeight },
    meridional: { x: leftWidth, y: bottomHeight, width: rightWidth, height: topHeight },
    "s_q": { x: 0, y: 0, width: leftWidth, height: bottomHeight },
    top: { x: leftWidth, y: 0, width: rightWidth, height: bottomHeight },
  };
}

export function visibleGeometricViews(layout) {
  return layout === "quad" || layout === "quad_stacked"
    ? ["3d", "meridional", "top"]
    : GEOMETRIC_VIEW_IDS.has(layout) ? [layout] : [];
}

export function viewportAtPointer(clientX, clientY, canvasRect, rects, viewIds) {
  if (!canvasRect?.width || !canvasRect?.height) {
    return null;
  }
  const allRects = Object.values(rects || {});
  const canvasWidth = Math.max(0, ...allRects.map((rect) => rect.x + rect.width));
  const canvasHeight = Math.max(0, ...allRects.map((rect) => rect.y + rect.height));
  const x = (clientX - canvasRect.left) * (canvasWidth / canvasRect.width);
  const y = (canvasRect.top + canvasRect.height - clientY) * (canvasHeight / canvasRect.height);
  for (const viewId of viewIds || []) {
    const rect = rects?.[viewId];
    if (!rect?.width || !rect?.height) {
      continue;
    }
    if (
      coordinateInsideViewport(x, rect.x, rect.width, canvasWidth) &&
      coordinateInsideViewport(y, rect.y, rect.height, canvasHeight)
    ) {
      return {
        viewId,
        pointer: {
          x: ((x - rect.x) / rect.width) * 2 - 1,
          y: ((y - rect.y) / rect.height) * 2 - 1,
        },
      };
    }
  }
  return null;
}

export function orthographicCameraFrame(bounds, viewId, aspect) {
  const radius = Math.max(Number(bounds.radius) || 1, 1);
  const distance = radius * 4;
  if (viewId === "top") {
    return {
      position: [0, 0, distance],
      target: [0, 0, 0],
      up: [0, 1, 0],
      halfHeight: radius * 1.15,
      aspect,
    };
  }
  return {
    position: [0, -distance, 0],
    target: [0, 0, 0],
    up: [0, 0, 1],
    halfHeight: radius * 1.15,
    aspect,
  };
}

function finiteDimension(value) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.max(0, Math.floor(number)) : 0;
}

function coordinateInsideViewport(coordinate, start, size, canvasSize) {
  const end = start + size;
  return coordinate >= start && (coordinate < end || (end === canvasSize && coordinate === end));
}
