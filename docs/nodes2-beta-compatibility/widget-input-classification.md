# Widget/input classification

PRIMARY: model, inference_method, prompt, resolution, aspect_ratio, duration, seed, generate_audio; optional exact geometry size; control after generate (Classic combo, Beta native seed-linked control).
SOCKET_ONLY: first_frame, last_frame, source_video, reference_N (IMAGE/VIDEO/AUDIO/INPUT_REFERENCE union native inputs as method permits). Legacy input_references collection retains link/serialized semantics, no phantom body widget.
OUTPUT_ONLY: VIDEO, JOB_ID, MODEL, ACTUAL_COST_USD, STATUS.
INTERNAL_HIDDEN: first_frame_url, last_frame_url legacy STRING backing slots (serialize=true, old workflow compatibility); Advanced compatibility button (serialize=false); COST estimate state (serialize=false); empty REFERENCES summary (serialize=false); empty STATE capability disclosure (serialize=false).
INTENTIONAL_READONLY_DISCLOSURE: nonempty reference summary and capability validation states. Not editable controls.
ADVANCED: no hidden implementation backing state may appear when native Show advanced inputs is open. Existing native non-widget source/legacy media inputs are projected by method/link authority; not converted to form fields.

Exact blank identification: REFERENCES text widget, no INPUT_TYPES input declaration, frontend onNodeCreated addReadOnlyWidget. It exists solely to display counts when applicable. Classic setVisible sets item.hidden and computeSize=-4. Beta useGraphNodeManager projects options.hidden, not item.hidden. STATE uses the same mechanism. Advanced is a nonserialized positional compatibility slot; COST is nonserialized local pricing backing state. Preserve saved semantic values, not visible blank rows.

Media duplicate identification: first_frame_url / last_frame_url are legacy STRING advanced inputs with display_name first_frame / last_frame. Native first_frame / last_frame are distinct IMAGE_OR_INPUT_REFERENCE sockets. Removing the backend URL inputs would break historical workflows. Keep their state and migration/serialization, suppress presentation in both renderers. New media entry remains sockets only. No Python or media transport changes needed.
