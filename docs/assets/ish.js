// File: docs/assets/ish.js
// This script should be loaded after p5.js library is loaded.
// It defines the animation but does not run it until initializeIshAnimation is called.

function initializeIshAnimation(p5InstanceCreator) {
  if (!p5InstanceCreator) {
    console.error('ish.js: p5InstanceCreator (the p5 constructor) was not provided to initializeIshAnimation.');
    return;
  }
  console.log('ish.js: initializeIshAnimation called. p5InstanceCreator is:', typeof p5InstanceCreator);

  const sketch = (p) => {
    let cols, rows;
    let spacing = 30;
    let w = 1000;
    let h = 800;
    let allDots = [];

    let pulses = [];
    let lastAutoPulse = 0;
    let sceneMode = "default"; // or "locked"

    const palette = ['#246BEE', '#3DD695', '#FD015F', '#FFA600'];

    p.setup = function() {
      try {
        let canvas = p.createCanvas(p.windowWidth, p.windowHeight, p.WEBGL);
        canvas.addClass('p5Canvas'); // Ensure class for CSS
        p.textFont('monospace');
        p.textAlign(p.CENTER, p.CENTER);
        cols = p.floor(w / spacing);
        rows = p.floor(h / spacing);

        for (let y = 0; y < rows; y++) {
          for (let x = 0; x < cols; x++) {
            let base = p.color(p.random(palette));
            let delay = p.dist(x * spacing, y * spacing, w / 2, h / 2) / 8 + p.random(30);
            allDots.push({
              x: x * spacing,
              y: y * spacing,
              z: 0,
              currentScale: 0,
              targetScale: 1,
              baseColor: base,
              hoverColor: base,
              hoverTimer: 0,
              currentColor: base,
              visible: false,
              revealFrame: p.frameCount + delay
            });
          }
        }
        console.log('ish.js: Sketch setup complete. Canvas created and class "p5Canvas" added.');
      } catch (e) {
        console.error('ish.js: Error in p.setup():', e);
      }
    };

    p.draw = function() {
      try {
        p.clear();
        let fc = p.frameCount;

        let zoomAmt = 0.5 + p.sin(fc * 0.004) * 0.3;

        if (sceneMode === "default") {
          let flattenOsc = p.sin(fc * 0.0025);
          let rotateXAmt = p.map(flattenOsc, -1, 1, 0.05, 0.35);
          let rotateZAmt = p.cos(fc * 0.0025) * 0.35;
          let zTranslate = zoomAmt * 250;
          let yCompensate = p.map(rotateXAmt, 0.05, 0.35, -30, 50, true);
          p.rotateX(p.PI / 5 + rotateXAmt);
          p.rotateZ(p.PI / 8 + rotateZAmt);
          p.translate(-w / 2, -h / 2 + yCompensate, zTranslate);
        } else if (sceneMode === "locked") {
          let zoomAmtLocked = 1.3; // Use a different variable name to avoid conflict if needed
          p.rotateX(p.PI / 4);
          p.rotateZ(p.PI / 10);
          p.translate(-w / 2, -h / 2, zoomAmtLocked * 250);
        }

        if (p.millis() - lastAutoPulse > 3000 && p.mouseX >= 0 && p.mouseX <= p.width && p.mouseY >= 0 && p.mouseY <= p.height) {
          let mx = p.mouseX - p.width / 2;
          let my = p.mouseY - p.height / 2;
          let dot = getClosestDot(mx, my);
          if (dot) {
            pulses.push({ x: dot.x, y: dot.y, radius: 0 });
            lastAutoPulse = p.millis();
          }
        }

        for (let pulseItem of pulses) pulseItem.radius += 6; // Renamed 'pulse' to 'pulseItem'
        pulses = pulses.filter(pulseItem_1 => pulseItem_1.radius < 800); // Renamed 'pulse' to 'pulseItem_1'

        for (let dot of allDots) {
          if (fc >= dot.revealFrame) dot.visible = true;
          if (!dot.visible) continue;

          let pulseEffect = 0;
          for (let pulseItem_2 of pulses) { // Renamed 'pulse' to 'pulseItem_2'
            let d = p.dist(dot.x, dot.y, pulseItem_2.x, pulseItem_2.y);
            let diff = p.abs(d - pulseItem_2.radius);
            if (diff < 30) {
              pulseEffect = p.map(diff, 30, 0, 0, 1);
            }
          }

          let idleZ = p.sin(fc * 0.005 + (dot.x + dot.y) * 0.01) * 20;
          dot.z = idleZ;

          p.push();
          p.translate(dot.x, dot.y, dot.z);

          let localPulse = p.sin(fc * 0.1 + dot.x * 0.01 + dot.y * 0.01) * 0.3; // Renamed 'pulse' to 'localPulse'
          dot.targetScale = 1.0 + localPulse + pulseEffect * 1.5;
          dot.currentScale = p.lerp(dot.currentScale, dot.targetScale, 0.12);
          let scaleFactor = dot.currentScale;

          dot.hoverTimer = p.max(0, dot.hoverTimer - 0.02);
          let colorBlend = p.lerpColor(dot.baseColor, dot.hoverColor, dot.hoverTimer);
          dot.currentColor = p.lerpColor(dot.currentColor, colorBlend, 0.08);

          let alpha = p.map(scaleFactor, 0, 3.5, 0, 255);
          p.fill(dot.currentColor.levels[0], dot.currentColor.levels[1], dot.currentColor.levels[2], alpha);
          p.noStroke();
          p.ellipse(0, 0, 4 * scaleFactor, 4 * scaleFactor);

          p.pop();
        }
      } catch (e) {
        console.error('ish.js: Error in p.draw():', e);
        p.noLoop(); // Stop the animation if draw loop errors
      }
    };

    function getClosestDot(mx, my) {
      let closestDot = null;
      let minDist = Infinity;
      for (let dot of allDots) {
        if (!dot.visible) continue;
        let d = p.dist(dot.x - w / 2, dot.y - h / 2, mx, my);
        if (d < minDist) {
          minDist = d;
          closestDot = dot;
        }
      }
      return closestDot;
    }

    p.mousePressed = function() {
      try {
        let mX = p.mouseX - p.width / 2;
        let mY = p.mouseY - p.height / 2;
        let closest = getClosestDot(mX, mY);
        if (closest) {
          pulses.push({ x: closest.x, y: closest.y, radius: 0 });
        }
        console.log('ish.js: Canvas clicked.');
      } catch (e) {
        console.error('ish.js: Error in p.mousePressed():', e);
      }
    };

    p.windowResized = function() {
      try {
        p.resizeCanvas(p.windowWidth, p.windowHeight);
        console.log('ish.js: Window resized.');
        // Optionally, re-initialize or adjust elements based on new size
        // For example, if dot positions depend on canvas size, they might need updating.
        // restart(); // If a full restart is desired on resize.
      } catch (e) {
        console.error('ish.js: Error in p.windowResized():', e);
      }
    };
  }; // End of sketch function definition

  // Create and store the p5 instance using the passed-in constructor
  if (window.myP5Instance) {
    console.log('ish.js: Removing existing p5 instance before creating a new one.');
    window.myP5Instance.remove();
  }
  try {
    window.myP5Instance = new p5InstanceCreator(sketch);
  } catch (e) {
    console.error('ish.js: Error creating new p5 instance:', e);
  }
}

window.initializeIshAnimation = initializeIshAnimation;

