uniform mat4 u_model;
uniform mat4 u_view;
uniform mat4 u_projection;

attribute vec3 a_position;
attribute vec3 a_normal;
attribute vec2 a_texcoord;
attribute float a_face_label;

varying vec3 v_position;
varying vec3 v_normal;
varying vec2 v_texcoord;
varying float v_face_label;

void main() {
    vec4 world_pos = u_model * vec4(a_position, 1.0);
    v_position = world_pos.xyz;
    v_normal = mat3(u_model) * a_normal;
    v_texcoord = a_texcoord;
    v_face_label = a_face_label;
    gl_Position = u_projection * u_view * world_pos;
}
