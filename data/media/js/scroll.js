class ScrollObserver {
    isLoaded = false;
    hasMathJax = false;

    constructor() {
        window.document.addEventListener("DOMContentLoaded", (e) => {
            this.isLoaded = true;

            // configure MathJax
            if (typeof this.hasMathJax === "undefined") {{
                this.hasMathJax = false;
                if (typeof MathJax !== "undefined") {
                    this.hasMathJax = typeof MathJax.Hub !== "undefined";
                }
                
                if (this.hasMathJax) {
                    MathJax.Hub.Config({ messageStyle: "none" });
                }
            }}
            this.scrollChanged();
            window.webkit.messageHandlers.rendered.postMessage("");
        });

        window.addEventListener('scroll', (e) => {
            this.scrollChanged();
        });

    }

    get canScroll() {
        return document.documentElement.scrollHeight > document.documentElement.clientHeight;
    }

    get wasRendered() {
        return typeof isRendered !== "undefined" && isRendered;
    }

    get isRendered() {
        return this.wasRendered || !this.hasMathJax || MathJax.Hub.queue.running == 0 && MathJax.Hub.queue.pending == 0;
    }

    get getScroll() {
        if (this.canScroll && this.isRendered) {
            let e = document.documentElement;
            return e.scrollTop / (e.scrollHeight - e.clientHeight);
        } else {
            return 0;
        }
    }

    scrollChanged() {
        window.webkit.messageHandlers.scrollChanged.postMessage(this.getScroll);
    }

    setScrollScale(scale) {
        if (this.canScroll) {{
            let e = document.documentElement;
            e.scrollTop = (e.scrollHeight - e.clientHeight) * scale;
        }}
    }
}

const observer = new ScrollObserver();
