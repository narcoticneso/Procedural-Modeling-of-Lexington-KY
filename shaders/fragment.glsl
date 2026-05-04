uniform sampler2D u_tex_wall;
uniform sampler2D u_tex_roof;
uniform sampler2D u_tex_window;
uniform sampler2D u_tex_door;
uniform sampler2D u_tex_ground;
uniform sampler2D u_tex_wall_concrete;
uniform sampler2D u_tex_wall_glass;

uniform vec3 u_light_dir;
uniform vec3 u_light_color;
uniform vec3 u_ambient;
uniform vec3 u_camera_pos;

varying vec3 v_position;
varying vec3 v_normal;
varying vec2 v_texcoord;
varying float v_face_label;

void main() {
    int label = int(v_face_label + 0.5);

    vec4 tex_color;
    float specular_strength;

    if (label == 0) {
        tex_color = texture2D(u_tex_wall, v_texcoord);
        specular_strength = 0.1;
    } else if (label == 1) {
        tex_color = texture2D(u_tex_roof, v_texcoord);
        specular_strength = 0.05;
    } else if (label == 2) {
        tex_color = texture2D(u_tex_window, v_texcoord);
        specular_strength = 0.8;
    } else if (label == 3) {
        tex_color = texture2D(u_tex_door, v_texcoord);
        specular_strength = 0.2;
    } else if (label == 4) {
        tex_color = texture2D(u_tex_ground, v_texcoord);
        specular_strength = 0.0;
    } else if (label == 5) {
        tex_color = texture2D(u_tex_wall_concrete, v_texcoord);
        specular_strength = 0.05;
    } else if (label == 6) {
        tex_color = texture2D(u_tex_wall_glass, v_texcoord);
        specular_strength = 0.6;
    } else {
        tex_color = vec4(1.0, 0.0, 1.0, 1.0);
        specular_strength = 0.0;
    }

    vec3 normal = normalize(v_normal);
    vec3 light_dir = normalize(u_light_dir);

    vec3 ambient = u_ambient * tex_color.rgb;

    float diff = max(dot(normal, light_dir), 0.0);
    vec3 diffuse = diff * u_light_color * tex_color.rgb;

    vec3 view_dir = normalize(u_camera_pos - v_position);
    vec3 reflect_dir = reflect(-light_dir, normal);
    float spec = pow(max(dot(view_dir, reflect_dir), 0.0), 32.0);
    vec3 specular = specular_strength * spec * u_light_color;

    vec3 result = ambient + diffuse + specular;
    gl_FragColor = vec4(result, tex_color.a);
}
