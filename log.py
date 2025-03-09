class Logger:
    """
    Logs important state changes during gameplay to provide context for higher-level decision making.
    Tracks:
    1. Game state changes (overworld, scripted, dialog, menu)
    2. Player position changes (map, x, y, facing)
    """
    
    def __init__(self):
        """
        Initialize the logger with empty logs and specified max entries.
        """
        self.logs = {
            'state': [],
            'position': [],
            'button': []
        }

    def log_update(self, state):
        # Log State
        if not self.logs['state'] or self.logs['state'][-1][1] != state.data['state']:
            self.logs['state'].append((state.data['frame'], state.data['state']))
        # Log Position
        if not self.logs['position'] or (
            self.logs['position'][-1][1] != state.data['map']['name'] or 
            self.logs['position'][-1][2] != state.data['player']['position']
        ):
            if state.data['map']['dimensions'] != (0,0):
                self.logs['position'].append((state.data['frame'], state.data['map']['name'], state.data['player']['position']))
        # Log Buttons
        if not self.logs['button'] or self.logs['button'][-1][1] != state.data['last_button']:
            self.logs['button'].append((state.data['frame'], state.data['last_button']))

    def get_recent(self, log, count):
        return log[-count:]
    
    def clear_logs(self):
        """Clear all logs."""
        self.state_log = []
        self.logs['position'] = []
    
    def __str__(self, n = 10):
        """Return a string representation of last n log entries."""
        output = "=== Recent State Changes ===\n"
        for frame, state in self.get_recent(self.logs['state'], n):
            output += f"Frame {frame}: {state}\n"
        
        output += "\n=== Recent Position Changes ===\n"
        for frame, map_name, position in self.get_recent(self.logs['position'], n):
            x, y, facing = position
            output += f"Frame {frame}: {map_name} ({x}, {y}, {facing})\n"

        output += "\n=== Recent Buttons ===\n"
        for frame, button in self.get_recent(self.logs['button'], n):
            output += f"Frame {frame}: {button}\n"
        
        return output