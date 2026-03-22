- increase the smooth second hand motion to 15fps

- Show the current agenda item text as "Now: {event title}"

- let the users set the min and max radius percentage of the hour and minute markers, we currently set the length and outer radius. The length of the markers should be defined by the inner and outer radius percentage, so that users can create styles with very long or short markers, or even have the hour markers be longer than the minute markers. This also allows for more creative freedom in marker placement, such as having the hour markers be closer to the center than the minute markers.

- separate the hour marker and the hour text into two different layers, so that users can have the hour text be closer to the center than the hour markers, or even have the hour text be outside of the hour markers. This also allows for more creative freedom in marker placement, such as having the hour text be closer to the center than the minute markers, while the hour markers are further out.

- when changing the time zone, the clock should smoothly transition to the new time instead of jumping, this can be done by calculating the time difference and animating the hands to the new position over a short duration (e.g., 1 second) using an easing function for a smooth effect.