import { OrbState } from './orbStates';

type Listener = () => void;

export class OrbController {
  private _currentState: OrbState = 'idle';
  private _customLabel?: string;
  private _customDesc?: string;
  private _listeners: Set<Listener> = new Set();
  
  // Track amplitude directly so the animation loop can read it without React overhead
  public ttsAmplitude: number = 0;
  public userAmplitude: number = 0;

  // Callbacks for decoupling from React props
  public onAudioReady?: (audioBase64: string) => void;
  public onBargeIn?: () => void;
  public activeAudioElement: HTMLAudioElement | null = null;

  get currentState() { return this._currentState; }
  get customLabel() { return this._customLabel; }
  get customDesc() { return this._customDesc; }

  setState(state: OrbState | ((prev: OrbState) => OrbState)) {
    const newState = typeof state === 'function' ? state(this._currentState) : state;
    if (this._currentState !== newState) {
      this._currentState = newState;
      this.notify();
    }
  }

  setLabels(label?: string, desc?: string) {
    if (this._customLabel !== label || this._customDesc !== desc) {
      this._customLabel = label;
      this._customDesc = desc;
      this.notify();
    }
  }

  subscribe(listener: Listener) {
    this._listeners.add(listener);
    return () => { this._listeners.delete(listener); };
  }

  private notify() {
    for (const listener of this._listeners) {
      listener();
    }
  }
}
